"""Real PostgreSQL buckets in disposable schemas; all Cloudflare calls mocked."""
import asyncio
import base64
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event, func, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from backend.api import dependencies, images
from backend.core.security import create_access_token
from backend.database.ai_usage import DailyBudgetExceeded
from backend.database.dependencies import get_db
from backend.database.models import Base, Guest, Model, RateLimitBucket, User, UserRequest
from backend.database.rate_limiting import RateLimitExceeded, consume_bucket_token
from backend.main import app

PAYLOAD = {"success": True, "result": {"image": base64.b64encode(b"\xff\xd8\xffimage").decode()}}
D = Decimal


@pytest_asyncio.fixture
async def rate_db(budget_postgres_url):
    schema = "t2m_rate_test_" + uuid4().hex
    engine = create_async_engine(
        budget_postgres_url, execution_options={"schema_translate_map": {"tests": schema}}
    )
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
        yield SimpleNamespace(engine=engine, factory=factory, schema=schema)
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


@pytest_asyncio.fixture
async def real_rate(client, rate_db, monkeypatch):
    async def override_db():
        async with rate_db.factory() as session:
            yield session
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(dependencies, "SessionLocal", rate_db.factory)
    monkeypatch.setattr(images, "check_generation_rate_limit", dependencies.check_generation_rate_limit)
    return rate_db


async def bucket_rows(db):
    async with db.factory() as session:
        return (await session.execute(select(
            RateLimitBucket.scope, RateLimitBucket.subject_key,
            RateLimitBucket.tokens, RateLimitBucket.updated_at,
        ).order_by(RateLimitBucket.scope, RateLimitBucket.subject_key))).all()


async def install_owner(client, db, authenticated):
    async with db.factory.begin() as session:
        if authenticated:
            owner = User(email="owner@example.com", password="unused")
        else:
            owner = Guest(guest_id=uuid4())
        session.add(owner)
        await session.flush()
        if authenticated:
            scope, key = "user", str(owner.id)
        else:
            scope, key = "guest", str(owner.guest_id)
    if authenticated:
        client.cookies.set("access_token", create_access_token({"sub": key}))
    else:
        client.cookies.set("guest_id", key)
    return scope, key


@pytest.mark.asyncio
@pytest.mark.parametrize("authenticated", [False, True])
async def test_first_request_then_refusal_and_rollback(client, real_rate, provider, authenticated):
    scope, key = await install_owner(client, real_rate, authenticated)
    requests = provider(lambda request: httpx.Response(200, json=PAYLOAD))
    body = {"prompt": "city", "user_id": 98765, "guest_id": str(uuid4())}
    headers = {"X-Forwarded-For": "203.0.113.99"}
    assert (await client.post("/Text-to-Masterpiece/generate", json=body, headers=headers)).status_code == 200
    before = await bucket_rows(real_rate)
    assert {(row.scope, row.subject_key) for row in before} == {(scope, key), ("ip", "127.0.0.1")}
    assert next(row.tokens for row in before if row.scope == scope) == D("0")
    assert next(row.tokens for row in before if row.scope == "ip") == D("4")
    second = await client.post("/Text-to-Masterpiece/generate", json=body, headers=headers)
    assert second.status_code == 429
    assert 1 <= int(second.headers["retry-after"]) <= 7
    # IP's tentative decrement and timestamp change have both rolled back.
    assert await bucket_rows(real_rate) == before
    assert len(requests) == 1
    images.reserve_generation_neurons.assert_awaited_once()


@pytest.mark.asyncio
async def test_new_guest_identity_is_committed_and_reused(client, real_rate, provider):
    requests = provider(lambda request: httpx.Response(200, json=PAYLOAD))
    assert (await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})).status_code == 200
    guest_uuid = client.cookies.get("guest_id")
    assert guest_uuid
    rows = await bucket_rows(real_rate)
    assert ("guest", guest_uuid) in {(row.scope, row.subject_key) for row in rows}
    async with real_rate.factory() as session:
        guest = (await session.execute(select(Guest))).scalar_one()
        history = (await session.execute(select(UserRequest))).scalar_one()
        assert history.guest_id == guest.id and str(guest.guest_id) == guest_uuid
    assert (await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})).status_code == 429
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_refilled_owner_can_generate_again(client, real_rate, provider):
    requests = provider(lambda request: httpx.Response(200, json=PAYLOAD))
    assert (await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})).status_code == 200
    async with real_rate.factory.begin() as session:
        await session.execute(update(RateLimitBucket).where(RateLimitBucket.scope == "guest").values(
            updated_at=func.statement_timestamp() - text("INTERVAL '7 seconds'"),
        ))
    assert (await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})).status_code == 200
    assert len(requests) == 2
    assert next(row.tokens for row in await bucket_rows(real_rate) if row.scope == "guest") == D("0")


@pytest.mark.asyncio
async def test_ip_refusal_preserves_owner_and_does_not_reserve_neurons(client, real_rate, provider):
    scope, key = await install_owner(client, real_rate, True)
    # Exhaust a shared IP independently of this owner's unused bucket.
    async with real_rate.factory.begin() as session:
        await consume_bucket_token(session, "user", key, 2, D("1"), D("7"))
        session.add(RateLimitBucket(scope="ip", subject_key="127.0.0.1", tokens=D("0"),
                                    updated_at=func.statement_timestamp()))
    before = await bucket_rows(real_rate)
    requests = provider(lambda request: pytest.fail("Must not call provider"))
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 2
    assert await bucket_rows(real_rate) == before
    images.reserve_generation_neurons.assert_not_awaited()
    assert not requests


@pytest.mark.asyncio
async def test_owner_refusal_rolls_back_new_ip_bucket(client, real_rate, provider):
    scope, key = await install_owner(client, real_rate, True)
    async with real_rate.factory.begin() as session:
        session.add(RateLimitBucket(
            scope=scope, subject_key=key, tokens=D("0"),
            updated_at=func.statement_timestamp(),
        ))
    before = await bucket_rows(real_rate)
    requests = provider(lambda request: pytest.fail("Must not call provider"))
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == 429
    assert await bucket_rows(real_rate) == before
    assert not requests
    images.reserve_generation_neurons.assert_not_awaited()


@pytest.mark.asyncio
async def test_ip_capacity_limits_rotating_guests(client, real_rate, provider):
    requests = provider(lambda request: httpx.Response(200, json=PAYLOAD))
    for _ in range(5):
        client.cookies.delete("guest_id")
        response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
        assert response.status_code == 200
    client.cookies.delete("guest_id")
    before = await bucket_rows(real_rate)
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == 429 and "retry-after" in response.headers
    assert await bucket_rows(real_rate) == before
    assert len(requests) == images.reserve_generation_neurons.await_count == 5


@pytest.mark.asyncio
async def test_refill_saturates_and_refusal_does_not_modify_bucket(rate_db):
    async with rate_db.factory.begin() as session:
        assert await consume_bucket_token(session, "ip", "address", 5, D("45"), D("60")) == D("4")
        await session.execute(update(RateLimitBucket).values(
            tokens=D("0"), updated_at=func.statement_timestamp() - text("INTERVAL '1 hour'"),
        ))
    async with rate_db.factory.begin() as session:
        assert await consume_bucket_token(session, "ip", "address", 5, D("45"), D("60")) == D("4")
    # A fresh single-token bucket starts with its first token already spent.
    async with rate_db.factory.begin() as session:
        assert await consume_bucket_token(session, "user", "1", 1, D("1"), D("7")) == D("0")
    before = await bucket_rows(rate_db)
    with pytest.raises(RateLimitExceeded) as exc:
        async with rate_db.factory.begin() as session:
            await consume_bucket_token(session, "user", "1", 1, D("1"), D("7"))
    assert 1 <= exc.value.retry_after <= 7
    assert await bucket_rows(rate_db) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("authenticated", [False, True])
@pytest.mark.parametrize("existing_bucket", [False, True])
async def test_concurrent_requests_only_one_can_pass(
    client, real_rate, provider, authenticated, existing_bucket
):
    scope, key = await install_owner(client, real_rate, authenticated)
    if existing_bucket:
        async with real_rate.factory.begin() as session:
            session.add(RateLimitBucket(
                scope=scope, subject_key=key, tokens=D("1"),
                updated_at=func.statement_timestamp(),
            ))
    requests = provider(lambda request: httpx.Response(200, json=PAYLOAD))
    responses = await asyncio.gather(*[
        client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"}) for _ in range(2)
    ])
    assert sorted(response.status_code for response in responses) == [200, 429]
    assert len(requests) == 1
    images.reserve_generation_neurons.assert_awaited_once()
    assert next(row.tokens for row in await bucket_rows(real_rate) if row.scope == "ip") == D("4")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["provider", "daily-budget"])
async def test_downstream_error_keeps_tokens_and_guest_cookie(client, real_rate, provider, failure):
    requests = provider(lambda request: httpx.Response(503, json={"success": False}))
    if failure == "daily-budget":
        images.reserve_generation_neurons.side_effect = DailyBudgetExceeded()
    first = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert first.status_code == (502 if failure == "provider" else 429)
    assert client.cookies.get("guest_id") and "set-cookie" in first.headers
    before = await bucket_rows(real_rate)
    second = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert second.status_code == 429 and "retry-after" in second.headers
    assert await bucket_rows(real_rate) == before
    images.reserve_generation_neurons.assert_awaited_once()
    assert len(requests) == (1 if failure == "provider" else 0)
    async with real_rate.factory() as session:
        assert not list(await session.scalars(select(UserRequest)))


@pytest.mark.asyncio
async def test_new_engine_keeps_rate_limit_state(client, real_rate, provider, monkeypatch):
    requests = provider(lambda request: httpx.Response(200, json=PAYLOAD))
    assert (await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})).status_code == 200
    before = await bucket_rows(real_rate)
    await real_rate.engine.dispose()
    restarted = create_async_engine(real_rate.engine.url, execution_options={
        "schema_translate_map": {"tests": real_rate.schema},
    })
    try:
        monkeypatch.setattr(dependencies, "SessionLocal", async_sessionmaker(restarted))
        response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
        assert response.status_code == 429
        assert await bucket_rows(real_rate) == before
        assert len(requests) == 1
    finally:
        await restarted.dispose()


@pytest.mark.asyncio
async def test_failed_commit_blocks_budget_and_provider(client, real_rate, provider, monkeypatch):
    class FailingSession(Session):
        pass
    def fail_commit(session):
        raise OperationalError("COMMIT", {}, Exception("injected failure"))
    event.listen(FailingSession, "before_commit", fail_commit)
    monkeypatch.setattr(dependencies, "SessionLocal", async_sessionmaker(
        real_rate.engine, sync_session_class=FailingSession,
    ))
    requests = provider(lambda request: pytest.fail("Must not call provider"))
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == 503
    # Owner identity was committed before entering the failing rate transaction.
    assert not requests and "set-cookie" in response.headers
    assert await bucket_rows(real_rate) == []
    images.reserve_generation_neurons.assert_not_awaited()
    async with real_rate.factory() as session:
        assert len(list(await session.scalars(select(Guest)))) == 1


@pytest.mark.asyncio
async def test_rate_commit_precedes_daily_budget(client, real_rate, provider):
    async def reserve(cost, daily_limit):
        # Independent connection sees both committed buckets, with no row lock
        # retained by the rate limiter while reserving Neurons or calling AI.
        async with real_rate.factory.begin() as session:
            await session.execute(text("SET LOCAL lock_timeout = '500ms'"))
            rows = (await session.execute(select(RateLimitBucket).with_for_update())).scalars().all()
            assert len(rows) == 2
    images.reserve_generation_neurons.side_effect = reserve
    provider(lambda request: httpx.Response(200, json=PAYLOAD))
    assert (await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})).status_code == 200
