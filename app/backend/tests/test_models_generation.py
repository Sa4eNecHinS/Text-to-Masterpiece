import base64
import json
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from backend.api import images
from backend.core.security import create_access_token
from backend.database.models import Guest, Model, User, UserRequest
from backend.services.image_generation import ImageGenerationError, generate_image

MODEL_IDS = ["cloudflare/flux-1-schnell", "cloudflare/flux-2-klein-4b"]
# Provider bytes pass through the same decoder/storage path for both models.
IMAGE = b"\xff\xd8\xff\xe0test-image\xff\xd9"
PAYLOAD = {"success": True, "result": {"image": base64.b64encode(IMAGE).decode()}}


def add_owner(db, authenticated, client):
    if authenticated:
        owner = User(email="owner@example.com", password="unused")
    else:
        owner = Guest(guest_id=uuid4())
    db.sync.add(owner)
    db.sync.commit()
    if authenticated:
        client.cookies.set("access_token", create_access_token({"sub": str(owner.id)}))
    else:
        client.cookies.set("guest_id", str(owner.guest_id))
    return owner


@pytest.mark.asyncio
async def test_models_public_database_catalogue(client, db):
    # The DB supplies display names; no provider IDs are exposed.
    db.sync.get(Model, MODEL_IDS[0]).name = "Name from PostgreSQL"
    db.sync.commit()
    response = await client.get("/Text-to-Masterpiece/models")
    assert response.status_code == 200
    assert response.json() == [
        {"model_id": MODEL_IDS[0], "name": "Name from PostgreSQL"},
        {"model_id": MODEL_IDS[1], "name": "FLUX-2-klein-4b"},
    ]
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_empty_catalogue(client, db):
    for model in db.sync.scalars(select(Model)):
        db.sync.delete(model)
    db.sync.commit()
    assert (await client.get("/Text-to-Masterpiece/models")).json() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("model_id", MODEL_IDS)
@pytest.mark.parametrize("authenticated", [False, True])
async def test_generate_and_history(client, db, tmp_path, provider, model_id, authenticated):
    owner = add_owner(db, authenticated, client)
    requests = provider(lambda request: httpx.Response(200, json=PAYLOAD))
    response = await client.post("/Text-to-Masterpiece/generate", json={
        "prompt": " A futuristic city ", "model_id": model_id,
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["model_id"] == model_id
    assert data["model_name"] == db.sync.get(Model, model_id).name
    assert list(tmp_path.iterdir())[0].read_bytes() == IMAGE
    assert data["image_url"].startswith("http://test/images/")
    request, = requests
    assert str(request.url).endswith(db.sync.get(Model, model_id).provider_model_id)
    if model_id == MODEL_IDS[0]:
        assert request.headers["content-type"] == "application/json"
        assert json.loads(request.content) == {"prompt": "A futuristic city", "steps": 4}
    else:
        assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
        boundary = request.headers["content-type"].split("boundary=")[1]
        assert request.content.startswith(f"--{boundary}\r\n".encode())
        assert b'name="prompt"\r\n\r\nA futuristic city\r\n' in request.content
        assert b"filename=" not in request.content and b"steps" not in request.content
    row = db.sync.scalars(select(UserRequest)).one()
    assert row.model_id == model_id
    assert (row.user_id, row.guest_id) == ((owner.id, None) if authenticated else (None, owner.id))
    history = await client.get("/Text-to-Masterpiece/chat_history")
    assert history.status_code == 200
    assert history.json()[0]["model_id"] == model_id
    assert history.json()[0]["model_name"] == data["model_name"]


@pytest.mark.asyncio
async def test_legacy_request_creates_guest_and_uses_default(client, db, provider):
    requests = provider(lambda request: httpx.Response(200, json=PAYLOAD))
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == 200
    assert response.json()["model_id"] == MODEL_IDS[0]
    assert client.cookies.get("guest_id")
    assert len(requests) == 1
    assert db.sync.scalars(select(UserRequest)).one().guest_id is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["unknown", "missing-default", "provider", "provider_model_id", "extra-model"])
async def test_reject_model_before_provider(client, db, monkeypatch, tmp_path, kind):
    body = {"prompt": "city", "model_id": MODEL_IDS[0]}
    if kind == "unknown":
        body["model_id"] = "https://untrusted.example/evil"
    elif kind == "missing-default":
        db.sync.delete(db.sync.get(Model, MODEL_IDS[0]))
        del body["model_id"]
    elif kind == "extra-model":
        body["model_id"] = "cloudflare/unapproved"
        db.sync.add(Model(model_id=body["model_id"], name="Unapproved", provider="cloudflare",
                          provider_model_id="@cf/unapproved"))
    else:
        setattr(db.sync.get(Model, MODEL_IDS[0]), kind, "unapproved")
    db.sync.commit()
    credentials = AsyncMock(side_effect=AssertionError("Must validate before credentials"))
    monkeypatch.setattr(images, "cloudflare_credentials", credentials)
    generation = AsyncMock(side_effect=AssertionError("Must not call provider"))
    monkeypatch.setattr(images, "generate_image", generation)
    response = await client.post("/Text-to-Masterpiece/generate", json=body)
    assert response.status_code == 400
    credentials.assert_not_called()
    generation.assert_not_called()
    assert not list(db.sync.scalars(select(UserRequest)))
    assert not list(tmp_path.iterdir())
    catalogue = (await client.get("/Text-to-Masterpiece/models")).json()
    if kind in {"provider", "provider_model_id", "extra-model"}:
        assert all(model["model_id"] != body["model_id"] for model in catalogue)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"prompt": " "}, {"prompt": "x", "model_id": None}, {"prompt": "x", "model_id": ""},
])
async def test_invalid_input(client, body):
    assert (await client.post("/Text-to-Masterpiece/generate", json=body)).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("model_id", MODEL_IDS)
@pytest.mark.parametrize("failure", ["http", "success-false", "invalid-json", "bad-base64", "empty", "timeout"])
async def test_provider_failure_has_no_history(client, db, tmp_path, provider, model_id, failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if failure == "http":
            return httpx.Response(429, json={"success": False, "errors": [{"code": 1234}]})
        if failure == "success-false":
            return httpx.Response(200, json={"success": False})
        if failure == "invalid-json":
            return httpx.Response(200, text="not JSON")
        return httpx.Response(200, json={"success": True, "result": {
            "image": "???" if failure == "bad-base64" else "",
        }})
    provider(handler)
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city", "model_id": model_id})
    assert response.status_code == 502
    if failure == "http":
        assert "HTTP 429" in response.json()["detail"] and "1234" in response.json()["detail"]
    assert not list(db.sync.scalars(select(UserRequest)))
    # A verified guest identity is now committed before locking/rate limiting.
    assert len(list(db.sync.scalars(select(Guest)))) == 1
    assert client.cookies.get("guest_id")
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_database_failure_removes_image(client, db, provider, tmp_path, monkeypatch):
    provider(lambda request: httpx.Response(200, json=PAYLOAD))
    async def commit():
        if db.commit.await_count == 1:
            db.sync.commit()  # Owner verification succeeds.
        else:
            raise RuntimeError("history commit failed")
    monkeypatch.setattr(db, "commit", AsyncMock(side_effect=commit))
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == 500
    db.rollback.assert_awaited_once()
    assert not list(db.sync.scalars(select(UserRequest)))
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_storage_failure_has_no_history(client, db, provider, monkeypatch):
    provider(lambda request: httpx.Response(200, json=PAYLOAD))
    monkeypatch.setattr(images, "save_image", AsyncMock(side_effect=OSError("disk full")))
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == 500
    assert not list(db.sync.scalars(select(UserRequest)))


@pytest.mark.asyncio
@pytest.mark.parametrize("authenticated", [False, True])
async def test_legacy_history_pagination_and_ownership(client, db, authenticated):
    owner = add_owner(db, authenticated, client)
    ownership = {"user_id" if authenticated else "guest_id": owner.id}
    for day, model_id in [(1, None), (2, MODEL_IDS[1])]:
        db.sync.add(UserRequest(**ownership, prompt=f"day-{day}", image_url="/images/test.jpg",
                               model_id=model_id, created_at=datetime(2026, 1, day, tzinfo=timezone.utc)))
    other = Guest(guest_id=uuid4())
    db.sync.add(other)
    db.sync.flush()
    db.sync.add(UserRequest(guest_id=other.id, prompt="private", image_url="/images/private.jpg"))
    db.sync.commit()
    first = (await client.get("/Text-to-Masterpiece/chat_history?limit=1&offset=0")).json()
    second = (await client.get("/Text-to-Masterpiece/chat_history?limit=1&offset=1")).json()
    assert first[0]["prompt"] == "day-2" and first[0]["model_name"] == "FLUX-2-klein-4b"
    assert second[0]["prompt"] == "day-1"
    assert second[0]["model_id"] is None and second[0]["model_name"] is None
    assert (await client.get("/Text-to-Masterpiece/chat_history?offset=2")).json() == []


@pytest.mark.asyncio
async def test_service_rejects_arbitrary_provider_url(provider):
    requests = provider(lambda request: httpx.Response(200, json=PAYLOAD))
    with pytest.raises(ImageGenerationError, match="Unsupported"):
        await generate_image("city", "account", "token", "https://evil.example")
    assert not requests
