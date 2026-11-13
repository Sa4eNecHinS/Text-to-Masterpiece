"""Private S3 images: mock SDK only, no B2 credentials or network required."""
import asyncio
import threading
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.requests import ClientDisconnect

from backend.api import images
from backend.core.security import create_access_token
from backend.database.models import Chat, User, UserRequest
from backend.database.queries import add_user
from backend.services import image_storage
from backend.services.image_storage import StorageError, StoredImage, image_format
from backend.services.image_generation import ImageGenerationError
from backend.main import app

PNG = b"\x89PNG\r\n\x1a\nimage-data"
BASE = "/Text-to-Masterpiece"


async def generate(client, monkeypatch):
    monkeypatch.setattr(images, "generate_image", AsyncMock(return_value=PNG))
    response = await client.post(f"{BASE}/generate", json={"prompt": "city"})
    return response


@pytest.mark.asyncio
@pytest.mark.parametrize("authenticated", [False, True])
async def test_store_metadata_and_owner_download(client, db, storage, monkeypatch, authenticated):
    if authenticated:
        user = User(email="owner@example.com", password="unused")
        db.sync.add(user)
        db.sync.commit()
        client.cookies.set("access_token", create_access_token({"sub": str(user.id)}))
    response = await generate(client, monkeypatch)
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"generation_id", "chat_id", "model_id", "model_name"}
    row = db.sync.get(UserRequest, data["generation_id"])
    assert row.object_key.startswith("images/") and row.object_key.endswith(".png")
    UUID(row.object_key.removeprefix("images/").removesuffix(".png"))
    assert storage.objects[row.object_key] == (PNG, "image/png")
    assert "image_url" not in UserRequest.__table__.columns
    for path in [f"{BASE}/chat_history", f"{BASE}/chats/{data['chat_id']}"]:
        history = await client.get(path)
        assert history.status_code == 200
        assert history.json()[0]["id"] == row.id
        assert "object_key" not in history.text and "image_url" not in history.text
    async def download(key):
        assert not db.sync.in_transaction()
        return await image_storage.S3ImageStorage.download(storage, key)
    storage.download.side_effect = download
    image = await client.get(f"/images/{row.id}")
    assert image.status_code == 200 and image.content == PNG
    assert image.headers["content-type"] == "image/png"
    assert image.headers["cache-control"] == "private, no-store"
    assert image.headers["x-content-type-options"] == "nosniff"
    assert all(body.closed for body in storage.bodies)
    storage.upload.assert_awaited_once()  # History/read never re-upload.


@pytest.mark.asyncio
async def test_fresh_storage_instance_reads_existing_generation(client, storage, monkeypatch):
    data = (await generate(client, monkeypatch)).json()
    fresh = image_storage.S3ImageStorage(storage.client, "test-images")
    app.dependency_overrides[images.get_storage] = lambda: fresh
    assert (await client.get(f"/images/{data['generation_id']}")).content == PNG
    storage.upload.assert_awaited_once()


@pytest.mark.asyncio
async def test_foreign_missing_and_raw_key_are_not_accessible(client, db, storage, monkeypatch):
    data = (await generate(client, monkeypatch)).json()
    client.cookies.clear()
    other = User(email="other@example.com", password="unused")
    db.sync.add(other)
    db.sync.commit()
    for headers in [{}, {"Authorization": f"Bearer {create_access_token({'sub': str(other.id)})}"}]:
        response = await client.get(f"/images/{data['generation_id']}", headers=headers)
        assert response.status_code == 404 and response.json() == {"detail": "Image not found."}
    assert (await client.get("/images/999999")).status_code == 404
    assert (await client.get("/images/images/secret.png")).status_code == 404
    storage.download.assert_not_awaited()


@pytest.mark.asyncio
async def test_bearer_uses_existing_jwt_verification(client, db, monkeypatch):
    user = User(email="bearer@example.com", password="unused")
    db.sync.add(user)
    db.sync.commit()
    token = create_access_token({"sub": str(user.id)})
    client.cookies.set("access_token", token)
    data = (await generate(client, monkeypatch)).json()
    client.cookies.clear()
    assert (await client.get(f"/images/{data['generation_id']}", headers={"Authorization": f"Bearer {token}"})).content == PNG
    assert (await client.get(f"/images/{data['generation_id']}", headers={"Authorization": "Bearer invalid"})).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["registrate", "token"])
async def test_guest_image_survives_auth_transfer(client, db, storage, monkeypatch, action):
    if action == "token":
        await add_user("registered@example.com", "password123", db)
        await db.commit()
    data = (await generate(client, monkeypatch)).json()
    key = db.sync.get(UserRequest, data["generation_id"]).object_key
    assert (await client.get(f"/images/{data['generation_id']}")).status_code == 200
    if action == "registrate":
        auth = await client.post("/auth/Text-to-Masterpiece/registrate", json={"email": "registered@example.com", "password": "Password123!"})
    else:
        auth = await client.post("/auth/Text-to-Masterpiece/token", data={"username": "registered@example.com", "password": "password123"})
    assert auth.status_code == 200
    assert not client.cookies.get("guest_id") and client.cookies.get("access_token")
    assert (await client.get(f"/images/{data['generation_id']}")).content == PNG
    assert db.sync.get(UserRequest, data["generation_id"]).object_key == key
    storage.upload.assert_awaited_once()
    await client.post("/auth/Text-to-Masterpiece/logout")
    assert (await client.get(f"/images/{data['generation_id']}")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("uncertain", [False, True])
async def test_failed_upload_never_saves_a_success(client, db, storage, monkeypatch, caplog, uncertain):
    def fail(**options):
        if uncertain:
            storage.objects[options["Key"]] = (options["Body"], options["ContentType"])
            raise ReadTimeoutError(endpoint_url="https://example.invalid")
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "sensitive-provider-detail"}}, "PutObject")
    storage.client.put_object.side_effect = fail
    response = await generate(client, monkeypatch)
    assert response.status_code == 503
    assert "sensitive-provider-detail" not in response.text + caplog.text
    assert not list(db.sync.scalars(select(UserRequest)))
    assert not list(db.sync.scalars(select(Chat)))
    storage.delete.assert_not_awaited()  # Failed response is not proof of failed PUT.
    assert "inspect object_key=" in caplog.text
    images.reserve_generation_neurons.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [False, True])
async def test_download_errors_are_controlled(client, storage, monkeypatch, missing):
    data = (await generate(client, monkeypatch)).json()
    if missing:
        storage.objects.clear()
    else:
        storage.client.get_object.side_effect = ReadTimeoutError(endpoint_url="https://example.invalid")
    response = await client.get(f"/images/{data['generation_id']}")
    assert response.status_code == (404 if missing else 503)
    assert "object_key" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_failure", [False, True])
async def test_confirmed_rollback_compensates_and_logs_orphans(client, db, storage, monkeypatch, caplog, delete_failure):
    monkeypatch.setattr(images, "touch_chat", AsyncMock(side_effect=RuntimeError("before COMMIT")))
    if delete_failure:
        storage.delete.side_effect = StorageError("unavailable")
    response = await generate(client, monkeypatch)
    assert response.status_code == 500
    assert not list(db.sync.scalars(select(UserRequest)))
    assert not list(db.sync.scalars(select(Chat)))
    storage.delete.assert_awaited_once()
    assert bool(storage.objects) == delete_failure
    if delete_failure:
        assert "orphan object_key=" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("actually_committed", [False, True])
async def test_unknown_commit_never_deletes_a_potentially_referenced_object(client, db, storage, monkeypatch, caplog, actually_committed):
    async def commit():
        if db.commit.await_count == 1:
            db.sync.commit()
        else:
            if actually_committed:
                db.sync.commit()
            raise OperationalError("COMMIT", {}, Exception("connection lost"), connection_invalidated=True)
    monkeypatch.setattr(db, "commit", AsyncMock(side_effect=commit))
    response = await generate(client, monkeypatch)
    assert response.status_code == 500
    storage.delete.assert_not_awaited()
    assert len(storage.objects) == 1
    rows = list(db.sync.scalars(select(UserRequest)))
    assert bool(rows) == actually_committed
    if rows:
        assert rows[0].object_key in storage.objects
    assert "outcome unknown" in caplog.text


@pytest.mark.asyncio
async def test_definitive_commit_rejection_allows_compensation(client, db, storage, monkeypatch):
    async def commit():
        if db.commit.await_count == 1:
            db.sync.commit()
        else:
            raise IntegrityError("COMMIT", {}, SimpleNamespace(sqlstate="23514"))
    monkeypatch.setattr(db, "commit", AsyncMock(side_effect=commit))
    assert (await generate(client, monkeypatch)).status_code == 500
    storage.delete.assert_awaited_once()
    assert not storage.objects


@pytest.mark.asyncio
async def test_disconnect_before_stream_starts_closes_b2_body():
    body = BytesIO(PNG)
    response = images._ImageResponse(StoredImage(body, "image/png", len(PNG)))
    with pytest.raises(ClientDisconnect):
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, AsyncMock(), AsyncMock(side_effect=OSError("disconnected")))
    assert body.closed


@pytest.mark.asyncio
async def test_streaming_read_error_closes_body():
    body = Mock()
    body.read.side_effect = ReadTimeoutError(endpoint_url="https://example.invalid")
    image = StoredImage(body, "image/png")
    with pytest.raises(StorageError):
        async for _ in image.chunks():
            pass
    body.close.assert_called_once()


@pytest.mark.asyncio
async def test_download_is_chunked_and_closed(storage):
    data = PNG + b"x" * (150 * 1024)
    storage.objects["images/chunked.png"] = (data, "image/png")
    image = await storage.download("images/chunked.png")
    chunks = [chunk async for chunk in image.chunks()]
    assert b"".join(chunks) == data
    assert len(chunks) >= 3 and max(map(len, chunks)) <= 64 * 1024
    assert storage.bodies[0].closed


@pytest.mark.parametrize("data,mime,extension", [
    (PNG, "image/png", "png"), (b"\xff\xd8\xffimage", "image/jpeg", "jpg"),
    (b"RIFF0000WEBPimage", "image/webp", "webp"), (b"GIF89aimage", "image/gif", "gif"),
])
def test_actual_image_format(data, mime, extension):
    assert image_format(data) == (mime, extension)


@pytest.mark.asyncio
async def test_bad_image_format_not_uploaded(client, db, storage, monkeypatch):
    monkeypatch.setattr(images, "generate_image", AsyncMock(return_value=b"<svg>not allowed</svg>"))
    assert (await client.post(f"{BASE}/generate", json={"prompt": "city"})).status_code == 502
    storage.upload.assert_not_awaited()
    assert not list(db.sync.scalars(select(UserRequest)))


@pytest.mark.asyncio
async def test_cloudflare_failure_does_not_upload(client, db, storage, monkeypatch):
    monkeypatch.setattr(images, "generate_image", AsyncMock(side_effect=ImageGenerationError("provider failed")))
    assert (await client.post(f"{BASE}/generate", json={"prompt": "city"})).status_code == 502
    storage.upload.assert_not_awaited()
    assert not list(db.sync.scalars(select(UserRequest)))


@pytest.mark.asyncio
async def test_permission_denial_precedes_storage_resolution(client):
    def unavailable():
        raise AssertionError("Must not resolve storage for an unauthorized image")
    app.dependency_overrides[images.get_storage] = unavailable
    assert (await client.get("/images/1")).status_code == 404


@pytest.mark.asyncio
async def test_cancelled_get_closes_the_body_returned_by_worker(storage):
    entered, release = threading.Event(), threading.Event()
    body = BytesIO(PNG)
    def open_object(**kwargs):
        entered.set()
        assert release.wait(5)
        return {"Body": body, "ContentType": "image/png"}
    storage.client.get_object.side_effect = open_object
    task = asyncio.create_task(storage.download("images/test.png"))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert body.closed


@pytest.mark.asyncio
async def test_conditional_upload_does_not_overwrite(storage):
    storage.objects["images/existing.png"] = (PNG, "image/png")
    storage.client.put_object.side_effect = ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
    with pytest.raises(StorageError):
        await storage.upload("images/existing.png", b"replacement", "image/png")
    assert storage.objects["images/existing.png"] == (PNG, "image/png")
    assert storage.client.put_object.call_args.kwargs["IfNoneMatch"] == "*"


def test_sdk_client_is_explicit_and_reused(monkeypatch):
    image_storage.get_image_storage.cache_clear()
    sdk = Mock()
    factory = Mock(return_value=sdk)
    monkeypatch.setattr(image_storage.boto3, "client", factory)
    try:
        assert image_storage.get_image_storage() is image_storage.get_image_storage()
        factory.assert_called_once()
        options = factory.call_args.kwargs
        assert options["endpoint_url"] == "https://s3.example.invalid/"
        assert options["region_name"] == "test-region"
        assert options["aws_access_key_id"] == "test-key-id"
        assert options["aws_secret_access_key"] == "test-key"
        assert options["config"].connect_timeout == 5 and options["config"].read_timeout == 15
        assert options["config"].retries["total_max_attempts"] == 1
        assert options["config"].request_checksum_calculation == "when_required"
    finally:
        image_storage.get_image_storage.cache_clear()
