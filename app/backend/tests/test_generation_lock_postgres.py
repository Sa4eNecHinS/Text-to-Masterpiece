"""Independent PostgreSQL connections and the full /generate boundary; no real AI."""
import asyncio
from decimal import Decimal
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.api import dependencies, images
from backend.core.security import create_access_token
from backend.database.dependencies import get_db
from backend.database.generation_lock import (
    GLOBAL_GENERATION_NAMESPACE, GenerationAlreadyInProgress,
    GenerationCapacityExceeded, generation_lock, generation_lock_key,
)
from backend.database.models import AIDailyUsage, Base, Guest, Model, RateLimitBucket, User, UserRequest
from backend.main import app
from backend.services import ai_budget, image_generation


@pytest_asyncio.fixture
async def lock_db(budget_postgres_url):
    schema = "t2m_lock_test_" + uuid4().hex
    engine = create_async_engine(budget_postgres_url, pool_size=10, max_overflow=10, execution_options={
        "schema_translate_map": {"tests": schema},
    })
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.run_sync(Base.metadata.create_all)
    async with factory.begin() as session:
        session.add(Model(
            model_id="cloudflare/flux-1-schnell", name="FLUX.1-schnell",
            provider="cloudflare", provider_model_id="@cf/black-forest-labs/flux-1-schnell",
        ))
    try:
        yield SimpleNamespace(engine=engine, factory=factory)
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


@pytest_asyncio.fixture
async def real_locks(client, lock_db, monkeypatch):
    async def override_db():
        async with lock_db.factory() as session:
            yield session
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(dependencies, "SessionLocal", lock_db.factory)
    monkeypatch.setattr(ai_budget, "SessionLocal", lock_db.factory)
    monkeypatch.setattr(images, "generation_lock", partial(generation_lock, bind=lock_db.engine))
    monkeypatch.setattr(images, "check_generation_rate_limit", AsyncMock(wraps=dependencies.check_generation_rate_limit))
    monkeypatch.setattr(images, "reserve_generation_neurons", AsyncMock(wraps=ai_budget.reserve_generation_neurons))
    return lock_db


async def assert_all_slots_free(db):
    # Acquire all slots simultaneously on an independent connection: merely
    # acquiring one slot again could miss a leaked lock in a different slot.
    async with db.engine.connect() as connection:
        # Detect leaks even if the pool hands us a former lock-owning session
        # (reentrant acquisition on that same session would otherwise succeed).
        assert (await connection.execute(text(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
            "AND database = (SELECT oid FROM pg_database WHERE datname = current_database()) "
            "AND classid = :namespace AND objsubid = 2"
        ), {"namespace": GLOBAL_GENERATION_NAMESPACE})).scalar_one() == 0
        for slot in range(1, 6):
            assert (await connection.execute(
                text("SELECT pg_try_advisory_lock(:namespace, :slot)"),
                {"namespace": GLOBAL_GENERATION_NAMESPACE, "slot": slot},
            )).scalar_one() is True
        await connection.commit()
        for slot in range(5, 0, -1):
            assert (await connection.execute(
                text("SELECT pg_advisory_unlock(:namespace, :slot)"),
                {"namespace": GLOBAL_GENERATION_NAMESPACE, "slot": slot},
            )).scalar_one() is True
        await connection.commit()


async def install_owner(client, db, authenticated):
    async with db.factory.begin() as session:
        owner = User(email="owner@example.com", password="unused") if authenticated else Guest(guest_id=uuid4())
        session.add(owner)
        await session.flush()
        owner_id = owner.id
        cookie = create_access_token({"sub": str(owner_id)}) if authenticated else str(owner.guest_id)
    client.cookies.set("access_token" if authenticated else "guest_id", cookie)
    return "user" if authenticated else "guest", owner_id


async def refill(db):
    async with db.factory.begin() as session:
        await session.execute(update(RateLimitBucket).values(
            updated_at=text("statement_timestamp() - INTERVAL '1 minute'"),
        ))


async def limits(db):
    async with db.factory() as session:
        buckets = (await session.execute(select(
            RateLimitBucket.scope, RateLimitBucket.subject_key, RateLimitBucket.tokens, RateLimitBucket.updated_at,
        ).order_by(RateLimitBucket.scope))).all()
        usage = (await session.execute(select(AIDailyUsage.usage_date, AIDailyUsage.used_neurons))).all()
        return buckets, usage


@pytest.mark.asyncio
async def test_independent_sessions_contention_commit_and_reuse(lock_db):
    owner_id = uuid4().int % (2**63)
    key = generation_lock_key("user", owner_id)
    async with generation_lock("user", owner_id, bind=lock_db.engine) as lock:
        first = lock._connection
        assert not first.in_transaction()
        pid = (await first.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        await first.commit()
        # The first session committed twice but still owns the advisory lock.
        async with lock_db.engine.connect() as second:
            second_pid = (await second.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            assert second_pid != pid
            assert (await second.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})).scalar_one() is False
            assert (await second.execute(
                text("SELECT pg_try_advisory_lock(:namespace, :slot)"),
                {"namespace": GLOBAL_GENERATION_NAMESPACE, "slot": lock.slot},
            )).scalar_one() is False
            assert (await second.execute(text(
                "SELECT xact_start IS NULL FROM pg_stat_activity WHERE pid = :pid"
            ), {"pid": pid})).scalar_one() is True
            await second.commit()
        with pytest.raises(GenerationAlreadyInProgress):
            async with generation_lock("user", owner_id, bind=lock_db.engine):
                pytest.fail("Another physical session must not acquire this lock")
        async with generation_lock("user", owner_id + 1, bind=lock_db.engine):
            pass
        async with generation_lock("guest", owner_id, bind=lock_db.engine):
            pass
    async with generation_lock("user", owner_id, bind=lock_db.engine):
        pass


@pytest.mark.asyncio
async def test_global_slots_across_independent_pools_and_connections(lock_db):
    # A second pool simulates another worker, never a second production Engine.
    other_worker = create_async_engine(lock_db.engine.url)
    outcomes, pids = [], []
    ready, finish = asyncio.Event(), asyncio.Event()
    owner_base = uuid4().int % (2**62)

    async def attempt(index):
        engine = lock_db.engine if index % 2 == 0 else other_worker
        try:
            async with generation_lock("user", owner_base + index, bind=engine) as lock:
                pid = (await lock._connection.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                await lock._connection.commit()
                pids.append(pid)
                outcomes.append(lock.slot)
                if len(outcomes) == 6:
                    ready.set()
                await finish.wait()
        except GenerationCapacityExceeded:
            outcomes.append(None)
            if len(outcomes) == 6:
                ready.set()

    tasks = [asyncio.create_task(attempt(index)) for index in range(6)]
    try:
        await asyncio.wait_for(ready.wait(), 5)
        assert sorted(slot for slot in outcomes if slot is not None) == [1, 2, 3, 4, 5]
        assert outcomes.count(None) == 1
        assert len(set(pids)) == 5
    finally:
        finish.set()
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), 5)
        finally:
            await other_worker.dispose()
    await assert_all_slots_free(lock_db)


@pytest.mark.asyncio
async def test_five_users_run_sixth_refused_without_spending_then_reuses_slot(
    client, real_locks, monkeypatch, tmp_path
):
    entered = [asyncio.Event() for _ in range(6)]
    finish = [asyncio.Event() for _ in range(6)]
    active = maximum_active = 0

    async def generate(prompt, **kwargs):
        nonlocal active, maximum_active
        index = int(prompt)
        active += 1
        maximum_active = max(maximum_active, active)
        entered[index].set()
        try:
            await finish[index].wait()
            return b"image"
        finally:
            active -= 1
    provider = AsyncMock(side_effect=generate)
    monkeypatch.setattr(images, "generate_image", provider)
    async with real_locks.factory.begin() as session:
        owners = [User(email=f"owner-{index}@example.com", password="unused") for index in range(6)]
        session.add_all(owners)
        await session.flush()
        owner_ids = [owner.id for owner in owners]

    tasks = []
    async with AsyncExitStack() as stack:
        # Independent browser sessions and IPs, so a later retry is not masked
        # by the unchanged IP Token Bucket after five successful admissions.
        clients = [await stack.enter_async_context(httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(f"192.0.2.{index + 1}", 12345)),
            base_url="http://test",
            cookies={"access_token": create_access_token({"sub": str(owner_id)})},
        )) for index, owner_id in enumerate(owner_ids)]
        try:
            tasks = [asyncio.create_task(clients[index].post(
                "/Text-to-Masterpiece/generate", json={"prompt": str(index)},
            )) for index in range(5)]
            await asyncio.wait_for(asyncio.gather(*(event.wait() for event in entered[:5])), 5)
            before = await limits(real_locks)
            assert before[1][0].used_neurons == Decimal("325")
            sixth = await clients[5].post("/Text-to-Masterpiece/generate", json={"prompt": "5"})
            assert sixth.status_code == 503
            assert sixth.json() == {"detail": "Server is busy. Please try again later."}
            # Owner conflict takes precedence even when every global slot is busy.
            duplicate = await clients[0].post("/Text-to-Masterpiece/generate", json={"prompt": "0"})
            assert duplicate.status_code == 409
            assert await limits(real_locks) == before
            assert images.check_generation_rate_limit.await_count == 5
            assert images.reserve_generation_neurons.await_count == 5
            assert provider.await_count == 5
            assert not list(tmp_path.iterdir())
            async with real_locks.factory() as session:
                assert not list(await session.scalars(select(UserRequest)))

            # Capacity refusal must have released the sixth user's owner lock.
            key = generation_lock_key("user", owner_ids[5])
            async with real_locks.engine.connect() as observer:
                assert (await observer.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})).scalar_one()
                assert (await observer.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})).scalar_one()
                await observer.commit()
            finish[0].set()
            assert (await asyncio.wait_for(tasks[0], 5)).status_code == 200
            tasks.append(asyncio.create_task(clients[5].post(
                "/Text-to-Masterpiece/generate", json={"prompt": "5"},
            )))
            await asyncio.wait_for(entered[5].wait(), 5)
            assert active == 5
            assert maximum_active == 5
            assert provider.await_count == 6
            assert (await limits(real_locks))[1][0].used_neurons == Decimal("390")
        finally:
            for event in finish:
                event.set()
            responses = await asyncio.wait_for(asyncio.gather(*tasks), 5)
        assert all(response.status_code == 200 for response in responses)
    await assert_all_slots_free(real_locks)


@pytest.mark.asyncio
@pytest.mark.parametrize("authenticated", [False, True])
async def test_concurrent_generate_returns_409_without_spending(client, real_locks, monkeypatch, tmp_path, authenticated):
    kind, owner_id = await install_owner(client, real_locks, authenticated)
    entered, finish = asyncio.Event(), asyncio.Event()

    async def generate(**kwargs):
        # Check no application connection holds an open transaction during AI.
        async with real_locks.engine.connect() as observer:
            assert (await observer.execute(text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                "AND state = 'idle in transaction'"
            ))).scalar_one() == 0
        entered.set()
        await finish.wait()
        return b"image"
    provider = AsyncMock(side_effect=generate)
    monkeypatch.setattr(images, "generate_image", provider)
    first = asyncio.create_task(client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"}))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        before = await limits(real_locks)
        second = await client.post("/Text-to-Masterpiece/generate", json={
            "prompt": "forest", "user_id": owner_id + 1, "guest_id": str(uuid4()),
        })
        assert second.status_code == 409
        assert second.json() == {"detail": "Image generation is already in progress."}
        assert await limits(real_locks) == before
        assert before[1][0].used_neurons == Decimal("65")
        images.check_generation_rate_limit.assert_awaited_once()
        images.reserve_generation_neurons.assert_awaited_once()
        provider.assert_awaited_once()
        assert not list(tmp_path.iterdir())
        async with real_locks.factory() as session:
            assert not list(await session.scalars(select(UserRequest)))
    finally:
        finish.set()
        first_response = await asyncio.wait_for(first, 5)
    assert first_response.status_code == 200, first_response.text
    async with generation_lock(kind, owner_id, bind=real_locks.engine):
        pass
    await refill(real_locks)
    assert (await client.post("/Text-to-Masterpiece/generate", json={"prompt": "again"})).status_code == 200
    assert provider.await_count == 2
    assert (await limits(real_locks))[1][0].used_neurons == Decimal("130")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["cloudflare", "timeout", "total-timeout", "storage", "history"])
async def test_generation_failures_release_lock(client, real_locks, provider, monkeypatch, tmp_path, failure):
    kind, owner_id = await install_owner(client, real_locks, False)

    async def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if failure == "total-timeout":
            await asyncio.sleep(10)
        return httpx.Response(503, json={"success": False})
    deadlines = []
    if failure == "total-timeout":
        timeout = asyncio.timeout
        def short_deadline(seconds):
            deadlines.append(seconds)
            return timeout(0.01)
        monkeypatch.setattr(image_generation.asyncio, "timeout", short_deadline)
    if failure in {"cloudflare", "timeout", "total-timeout"}:
        provider(handler)
    else:
        monkeypatch.setattr(images, "generate_image", AsyncMock(return_value=b"image"))
        if failure == "storage":
            monkeypatch.setattr(images, "save_image", AsyncMock(side_effect=OSError("disk full")))
        else:
            monkeypatch.setattr(images, "add_prompt_and_image", AsyncMock(side_effect=RuntimeError("history failed")))
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == (502 if failure in {"cloudflare", "timeout", "total-timeout"} else 500)
    if failure == "total-timeout":
        assert deadlines == [60.0]
    await assert_all_slots_free(real_locks)
    async with generation_lock(kind, owner_id, bind=real_locks.engine):
        pass
    async with real_locks.factory() as session:
        assert not list(await session.scalars(select(UserRequest)))
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_lost_postgres_session_prevents_cloudflare(client, real_locks, monkeypatch):
    kind, owner_id = await install_owner(client, real_locks, True)
    pid = None

    @asynccontextmanager
    async def tracked_lock(*args):
        nonlocal pid
        async with generation_lock(*args, bind=real_locks.engine) as lock:
            pid = (await lock._connection.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            await lock._connection.commit()
            yield lock

    async def reserve_and_disconnect(*args):
        await ai_budget.reserve_generation_neurons(*args)
        async with real_locks.engine.begin() as connection:
            assert (await connection.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})).scalar_one()
    monkeypatch.setattr(images, "generation_lock", tracked_lock)
    monkeypatch.setattr(images, "reserve_generation_neurons", reserve_and_disconnect)
    provider = AsyncMock()
    monkeypatch.setattr(images, "generate_image", provider)
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == 503
    provider.assert_not_awaited()
    await assert_all_slots_free(real_locks)
    async with generation_lock(kind, owner_id, bind=real_locks.engine):
        pass


@pytest.mark.asyncio
async def test_cancelled_generation_releases_lock(client, real_locks, monkeypatch):
    kind, owner_id = await install_owner(client, real_locks, True)
    entered = asyncio.Event()

    async def generate(**kwargs):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(images, "generate_image", generate)
    task = asyncio.create_task(client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"}))
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await assert_all_slots_free(real_locks)
    async with generation_lock(kind, owner_id, bind=real_locks.engine):
        pass
