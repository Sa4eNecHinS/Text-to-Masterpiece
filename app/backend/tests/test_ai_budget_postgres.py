"""Real PostgreSQL atomicity tests; never connect to the application's DB.

Uses a temporary local PostgreSQL cluster when binaries are installed, or an
explicit TEST_AI_DATABASE_URL. Every test uses a random, disposable schema;
SQLAlchemy maps both unqualified tables and `tests` to it; application tables are never touched.
"""
import asyncio
import base64
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from backend.api import images
from backend.database import ai_usage
from backend.database.ai_usage import DailyBudgetExceeded, reserve_daily_neurons
from backend.database.models import AIDailyUsage, UserRequest
from backend.services import ai_budget

IMAGE = b"\xff\xd8\xff\xe0test-image\xff\xd9"
PAYLOAD = {"success": True, "result": {"image": base64.b64encode(IMAGE).decode()}}


@pytest_asyncio.fixture
async def budget_db(budget_postgres_url):
    schema = "t2m_budget_test_" + uuid4().hex
    engine = create_async_engine(
        budget_postgres_url, execution_options={"schema_translate_map": {None: schema, "tests": schema}}
    )
    async with engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.run_sync(AIDailyUsage.__table__.create)
    try:
        yield SimpleNamespace(engine=engine, factory=async_sessionmaker(engine), schema=schema)
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


@pytest_asyncio.fixture
async def real_budget(client, budget_db, monkeypatch):
    monkeypatch.setattr(ai_budget, "SessionLocal", budget_db.factory)
    monkeypatch.setattr(images, "reserve_generation_neurons", ai_budget.reserve_generation_neurons)
    return budget_db


async def usage_rows(budget_db):
    async with budget_db.factory() as session:
        return (await session.execute(
            select(AIDailyUsage.usage_date, AIDailyUsage.used_neurons).order_by(AIDailyUsage.usage_date)
        )).all()


@pytest.mark.asyncio
async def test_first_and_repeated_generation(client, real_budget, provider, db):
    requests = provider(lambda request: httpx.Response(200, json=PAYLOAD))
    first = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert first.status_code == 200
    assert (await usage_rows(real_budget))[0].used_neurons == Decimal("65")
    second = await client.post("/Text-to-Masterpiece/generate", json={
        "prompt": "forest", "model_id": "cloudflare/flux-2-klein-4b", "cost": "0",
    })
    assert second.status_code == 200
    rows = await usage_rows(real_budget)
    assert len(rows) == 1 and rows[0].used_neurons == Decimal("175")
    assert len(requests) == 2
    history = list(db.sync.scalars(select(UserRequest)))
    assert [row.model_id for row in history] == ["cloudflare/flux-1-schnell", "cloudflare/flux-2-klein-4b"]


@pytest.mark.asyncio
async def test_api_budget_exhaustion(client, real_budget, provider, db, storage, monkeypatch):
    monkeypatch.setattr(images, "settings", SimpleNamespace(AI_DAILY_NEURON_LIMIT=Decimal("65")))
    requests = provider(lambda request: httpx.Response(200, json=PAYLOAD))
    first = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert first.status_code == 200
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == 429
    assert response.json()["detail"] == "Daily AI generation limit reached."
    assert len(requests) == 1
    assert len(storage.objects) == 1
    assert len(list(db.sync.scalars(select(UserRequest)))) == 1
    assert (await usage_rows(real_budget))[0].used_neurons == Decimal("65")


@pytest.mark.asyncio
async def test_provider_failure_keeps_committed_reservation(client, real_budget, provider, db, tmp_path):
    requests = provider(lambda request: httpx.Response(503, json={"success": False}))
    for expected in (Decimal("65"), Decimal("130")):
        response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
        assert response.status_code == 502
        assert (await usage_rows(real_budget))[0].used_neurons == expected
    assert len(requests) == 2
    assert not list(tmp_path.iterdir())
    assert not list(db.sync.scalars(select(UserRequest)))


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
async def test_concurrent_reservations_allow_only_one(budget_db, existing):
    cost = Decimal("65")
    if existing:
        async with budget_db.factory.begin() as session:
            await reserve_daily_neurons(session, cost, cost)
    limit = cost * (2 if existing else 1)
    start = asyncio.Event()
    async def attempt():
        await start.wait()
        async with budget_db.factory.begin() as session:
            return await reserve_daily_neurons(session, cost, limit)
    tasks = [asyncio.create_task(attempt()) for _ in range(2)]
    start.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert sum(isinstance(result, DailyBudgetExceeded) for result in results) == 1
    assert sum(result == limit for result in results) == 1
    assert (await usage_rows(budget_db))[0].used_neurons == limit


@pytest.mark.asyncio
async def test_concurrent_api_requests_allow_one_provider_call(
    client, real_budget, provider, db, storage, monkeypatch
):
    monkeypatch.setattr(
        images, "settings", SimpleNamespace(AI_DAILY_NEURON_LIMIT=Decimal("65"))
    )
    requests = provider(lambda request: httpx.Response(200, json=PAYLOAD))
    responses = await asyncio.gather(*[
        client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
        for _ in range(2)
    ])
    assert sorted(response.status_code for response in responses) == [200, 429]
    assert len(requests) == 1
    assert (await usage_rows(real_budget))[0].used_neurons == Decimal("65")
    assert len(storage.objects) == 1
    assert len(list(db.sync.scalars(select(UserRequest)))) == 1


@pytest.mark.asyncio
async def test_next_utc_day_preserves_previous_day(budget_db, monkeypatch):
    utc_date = ai_usage._utc_usage_date
    # Simulate the previous day on the database side, never the Python clock.
    monkeypatch.setattr(ai_usage, "_utc_usage_date", lambda: utc_date() - 1)
    async with budget_db.factory.begin() as session:
        await reserve_daily_neurons(session, Decimal("65"), Decimal("110"))
    monkeypatch.setattr(ai_usage, "_utc_usage_date", utc_date)
    async with budget_db.factory.begin() as session:
        # Local connection timezone must not affect the UTC bucket.
        await session.execute(text("SET LOCAL TIME ZONE 'Pacific/Honolulu'"))
        today = await session.scalar(select(utc_date()))
        await reserve_daily_neurons(session, Decimal("110"), Decimal("110"))
    rows = await usage_rows(budget_db)
    assert rows == [(today - timedelta(days=1), Decimal("65")), (today, Decimal("110"))]


@pytest.mark.asyncio
async def test_recreated_engine_keeps_budget(budget_db, monkeypatch):
    monkeypatch.setattr(ai_budget, "SessionLocal", budget_db.factory)
    await ai_budget.reserve_generation_neurons(Decimal("65"), Decimal("65"))
    await budget_db.engine.dispose()
    # New pool and session factory, as after a backend process restart.
    restarted = create_async_engine(
        budget_db.engine.url,
        execution_options={"schema_translate_map": {None: budget_db.schema, "tests": budget_db.schema}},
    )
    try:
        monkeypatch.setattr(ai_budget, "SessionLocal", async_sessionmaker(restarted))
        with pytest.raises(DailyBudgetExceeded):
            await ai_budget.reserve_generation_neurons(Decimal("65"), Decimal("65"))
        assert (await usage_rows(budget_db))[0].used_neurons == Decimal("65")
    finally:
        await restarted.dispose()


@pytest.mark.asyncio
async def test_reservation_function_does_not_commit(budget_db):
    async with budget_db.factory() as session:
        assert await reserve_daily_neurons(session, Decimal("0.25"), Decimal("1")) == Decimal("0.25")
        await session.rollback()
    assert await usage_rows(budget_db) == []
    async with budget_db.factory.begin() as session:
        with pytest.raises(DailyBudgetExceeded):
            await reserve_daily_neurons(session, Decimal("2"), Decimal("1"))
    assert await usage_rows(budget_db) == []


@pytest.mark.asyncio
async def test_commit_failure_blocks_provider(client, real_budget, monkeypatch, provider):
    class FailingSession(Session):
        pass
    def fail_commit(session):
        raise OperationalError("COMMIT", {}, Exception("injected commit failure"))
    event.listen(FailingSession, "before_commit", fail_commit)
    monkeypatch.setattr(ai_budget, "SessionLocal", async_sessionmaker(
        real_budget.engine, sync_session_class=FailingSession,
    ))
    requests = provider(lambda request: pytest.fail("Provider must not be called before COMMIT"))
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == 503
    assert not requests
    assert await usage_rows(real_budget) == []


@pytest.mark.asyncio
async def test_no_row_lock_is_held_during_provider_call(client, real_budget, monkeypatch):
    async def provider_call(**kwargs):
        # A second transaction can lock and update the same row immediately.
        async with real_budget.factory.begin() as session:
            await session.execute(text("SET LOCAL lock_timeout = '500ms'"))
            assert await reserve_daily_neurons(session, Decimal("65"), Decimal("130")) == Decimal("130")
        return IMAGE
    monkeypatch.setattr(images, "generate_image", provider_call)
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == 200
    assert (await usage_rows(real_budget))[0].used_neurons == Decimal("130")
