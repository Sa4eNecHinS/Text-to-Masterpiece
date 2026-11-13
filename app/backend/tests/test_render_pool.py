"""Production-size pool with real local PostgreSQL and mocked external I/O."""
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select, text

from backend.api import auth, images
from backend.core.security import create_access_token
from backend.database.generation_lock import generation_lock
from backend.database.models import User, UserRequest
from backend.main import app
from backend.tests.test_generation_lock_postgres import (
    assert_all_slots_free, install_owner, lock_db, real_locks,
)


@pytest.mark.asyncio
async def test_five_generations_and_auth_history_models_use_at_most_13(real_locks, monkeypatch):
    db = real_locks
    provider_ready = [asyncio.Event() for _ in range(5)]
    persistence_ready = [asyncio.Event() for _ in range(5)]
    other_ready = [asyncio.Event() for _ in range(3)]
    release_provider, release_sql = asyncio.Event(), asyncio.Event()
    queued_model_request = asyncio.Event()
    model_reads = 0

    async def generate(prompt, **kwargs):
        provider_ready[int(prompt)].set()
        await release_provider.wait()
        return b"\xff\xd8\xffmock-image"

    original_add = images.add_prompt_and_image

    async def save(**kwargs):
        result = await original_add(**kwargs)
        persistence_ready[int(kwargs["prompt"])].set()
        await release_sql.wait()  # Keep the real SQL transaction checked out.
        return result

    async def password(*args):
        other_ready[0].set()  # login has already SELECTed its user.
        await release_sql.wait()
        return True

    def held_read(original, index):
        async def read(*args, **kwargs):
            nonlocal model_reads
            if index == 2:
                model_reads += 1
                if model_reads == 2:
                    queued_model_request.set()
            result = await original(*args, **kwargs)
            other_ready[index].set()
            await release_sql.wait()
            return result
        return read

    monkeypatch.setattr(images, "generate_image", AsyncMock(side_effect=generate))
    monkeypatch.setattr(images, "add_prompt_and_image", save)
    monkeypatch.setattr(auth, "verify_password", password)
    monkeypatch.setattr(images, "get_user_chat_history", held_read(images.get_user_chat_history, 1))
    monkeypatch.setattr(images, "get_models", held_read(images.get_models, 2))

    async with db.factory.begin() as session:
        users = [User(email=f"pool-{i}@example.com", password="mock-password") for i in range(5)]
        session.add_all(users)
        await session.flush()
        ids = [user.id for user in users]

    tasks = []
    async with AsyncExitStack() as stack:
        clients = [await stack.enter_async_context(httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(f"192.0.2.{i + 1}", 12345)),
            base_url="http://test",
            cookies={"access_token": create_access_token({"sub": str(user_id)})},
        )) for i, user_id in enumerate(ids)]
        try:
            tasks = [asyncio.create_task(clients[i].post(
                "/Text-to-Masterpiece/generate", json={"prompt": str(i)},
            )) for i in range(5)]
            await asyncio.wait_for(asyncio.gather(*(e.wait() for e in provider_ready)), 10)
            assert db.engine.pool.checkedout() == 5
            release_provider.set()
            await asyncio.wait_for(asyncio.gather(*(e.wait() for e in persistence_ready)), 10)
            assert db.engine.pool.checkedout() == 10
            tasks.extend([
                asyncio.create_task(clients[0].post("/auth/Text-to-Masterpiece/token", data={
                    "username": "pool-0@example.com", "password": "mock-password",
                })),
                asyncio.create_task(clients[1].get("/Text-to-Masterpiece/chat_history")),
                asyncio.create_task(clients[2].get("/Text-to-Masterpiece/models")),
            ])
            await asyncio.wait_for(asyncio.gather(*(e.wait() for e in other_ready)), 10)
            assert db.engine.pool.checkedout() == 13
            assert db.metrics.peak == 13
            # A fourteenth checkout queues instead of creating another connection.
            queued = asyncio.create_task(clients[3].get("/Text-to-Masterpiece/models"))
            tasks.append(queued)
            await asyncio.wait_for(queued_model_request.wait(), 5)
            assert not queued.done()
            assert db.engine.pool.checkedout() == 13
            print(f"render pool: peak_checked_out={db.metrics.peak}")
        finally:
            release_provider.set()
            release_sql.set()
            results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 15)
        assert all(isinstance(result, httpx.Response) and result.status_code == 200 for result in results)
    async with db.factory() as session:
        assert len(list(await session.scalars(select(UserRequest)))) == 5
    await assert_all_slots_free(db)
    assert db.engine.pool.checkedout() == 0
    assert db.metrics.peak == 13


@pytest.mark.asyncio
async def test_lost_lock_after_upload_rolls_back_deletes_object_and_returns_503(
    client, real_locks, storage, monkeypatch,
):
    kind, owner_id = await install_owner(client, real_locks, True)
    tracked = {}

    @asynccontextmanager
    async def tracked_lock(*args):
        async with generation_lock(*args, bind=real_locks.engine) as lock:
            tracked["lock"] = lock
            tracked["pid"] = (await lock._connection.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            await lock._connection.commit()
            yield lock

    original_upload = storage.upload

    async def upload_then_disconnect(*args):
        await original_upload(*args)
        async with real_locks.engine.begin() as connection:
            assert (await connection.execute(text("SELECT pg_terminate_backend(:pid)"), {
                "pid": tracked["pid"],
            })).scalar_one()

    monkeypatch.setattr(images, "generation_lock", tracked_lock)
    monkeypatch.setattr(images, "generate_image", AsyncMock(return_value=b"\xff\xd8\xffmock-image"))
    monkeypatch.setattr(storage, "upload", upload_then_disconnect)
    persist = AsyncMock(wraps=images.add_prompt_and_image)
    monkeypatch.setattr(images, "add_prompt_and_image", persist)
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Generation locking is unavailable."
    persist.assert_not_awaited()
    storage.delete.assert_awaited_once()
    assert not storage.objects
    assert tracked["lock"]._connection.closed
    async with real_locks.factory() as session:
        assert not list(await session.scalars(select(UserRequest)))
    await assert_all_slots_free(real_locks)
    async with generation_lock(kind, owner_id, bind=real_locks.engine):
        pass
    assert real_locks.engine.pool.checkedout() == 0
