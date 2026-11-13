"""Lock lifecycle and fail-closed API boundaries, without a live database."""
import asyncio
import hashlib
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from backend.api import images
from backend.core.config import Settings, settings
from backend.database import generation_lock as locks
from backend.database.session import engine
from backend.database.models import UserRequest


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "NaN", "Infinity", "abc", "true", str(2**31)])
def test_invalid_concurrency_configuration(monkeypatch, value):
    monkeypatch.setenv("AI_MAX_CONCURRENT_GENERATIONS", value)
    with pytest.raises(ValidationError, match="AI_MAX_CONCURRENT_GENERATIONS"):
        Settings(_env_file=None)


def test_production_pool_defaults_and_connection_model(monkeypatch):
    for name in ("DB_POOL_SIZE", "DB_MAX_OVERFLOW", "DB_POOL_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)
    defaults = Settings(_env_file=None)
    assert (defaults.DB_POOL_SIZE, defaults.DB_MAX_OVERFLOW, defaults.DB_POOL_TIMEOUT) == (7, 6, 10)
    # One pinned connection + at most one SQL connection per generation;
    # one additional request each for auth, history and models.
    assert defaults.DB_POOL_SIZE + defaults.DB_MAX_OVERFLOW == 2 * 5 + 3
    assert engine.pool.size() == settings.DB_POOL_SIZE
    assert engine.pool._max_overflow == settings.DB_MAX_OVERFLOW
    assert engine.pool.timeout() == settings.DB_POOL_TIMEOUT
    assert engine.pool._pre_ping is True


def test_pool_environment_overrides_are_independent_of_generation_limit(monkeypatch):
    monkeypatch.setenv("DB_POOL_SIZE", "8")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "2.5")
    monkeypatch.setenv("AI_MAX_CONCURRENT_GENERATIONS", "7")
    configured = Settings(_env_file=None)
    assert (configured.DB_POOL_SIZE, configured.DB_MAX_OVERFLOW, configured.DB_POOL_TIMEOUT) == (8, 0, 2.5)
    assert configured.AI_MAX_CONCURRENT_GENERATIONS == 7


@pytest.mark.parametrize("name,value", [
    ("DB_POOL_SIZE", "0"), ("DB_POOL_SIZE", "-1"), ("DB_POOL_SIZE", "1.5"),
    ("DB_MAX_OVERFLOW", "-1"), ("DB_MAX_OVERFLOW", "1.5"),
    ("DB_POOL_TIMEOUT", "0"), ("DB_POOL_TIMEOUT", "-1"),
    ("DB_POOL_TIMEOUT", "NaN"), ("DB_POOL_TIMEOUT", "Infinity"),
])
def test_invalid_pool_configuration(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError, match=name):
        Settings(_env_file=None)


def test_owner_keys_are_stable_signed_and_namespaced():
    for kind in ("user", "guest"):
        for owner_id in (1, 2, 2**63 - 1):
            key = locks.generation_lock_key(kind, owner_id)
            expected = hashlib.sha256(f"t2m:generation:{kind}:{owner_id}".encode()).digest()
            assert key == int.from_bytes(expected[:8], "big", signed=True)
            assert -(2**63) <= key < 2**63
    assert locks.generation_lock_key("user", 1) != locks.generation_lock_key("guest", 1)


@pytest.fixture
def connection():
    return SimpleNamespace(
        closed=False, invalidated=False,
        execute=AsyncMock(return_value=Mock(scalar_one=lambda: True)),
        commit=AsyncMock(), invalidate=AsyncMock(), close=AsyncMock(),
    )


def bind(connection):
    return SimpleNamespace(connect=AsyncMock(return_value=connection))


@pytest.mark.asyncio
async def test_same_connection_committed_and_unlocked_before_pool_return(connection):
    async with locks.generation_lock("user", 1, bind=bind(connection)):
        connection.commit.assert_awaited_once()
        connection.close.assert_not_awaited()
        connection.invalidate.assert_not_awaited()
    assert connection.commit.await_count == 2
    assert "pg_try_advisory_lock" in str(connection.execute.await_args_list[0].args[0])
    calls = connection.execute.await_args_list
    assert calls[1].args[1] == {"namespace": 1487001, "slot": 1}
    assert "pg_advisory_unlock" in str(calls[2].args[0])
    assert calls[2].args[1] == {"namespace": 1487001, "slot": 1}
    assert calls[3].args[1] == {"key": locks.generation_lock_key("user", 1)}
    connection.close.assert_awaited_once()
    connection.invalidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_busy_connection_is_returned_without_unlocking(connection):
    connection.execute.side_effect = [Mock(scalar_one=lambda: False)]
    with pytest.raises(locks.GenerationAlreadyInProgress):
        async with locks.generation_lock("guest", 1, bind=bind(connection)):
            pytest.fail("Must not enter generation")
    connection.execute.assert_awaited_once()
    connection.close.assert_awaited_once()
    connection.invalidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_slots_are_probed_in_order_and_only_acquired_slot_is_released(connection):
    yes, no = Mock(scalar_one=lambda: True), Mock(scalar_one=lambda: False)
    connection.execute.side_effect = [yes, no, no, no, no, yes, yes, yes]
    async with locks.generation_lock("user", 1, bind=bind(connection)) as lock:
        assert lock.slot == 5
    calls = connection.execute.await_args_list
    assert [call.args[1]["slot"] for call in calls[1:6]] == [1, 2, 3, 4, 5]
    assert calls[6].args[1] == {"namespace": 1487001, "slot": 5}
    assert calls[7].args[1] == {"key": locks.generation_lock_key("user", 1)}
    connection.invalidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_global_slot_releases_owner_and_connection(connection):
    yes, no = Mock(scalar_one=lambda: True), Mock(scalar_one=lambda: False)
    connection.execute.side_effect = [yes, no, no, no, no, no, yes]
    with pytest.raises(locks.GenerationCapacityExceeded):
        async with locks.generation_lock("user", 1, bind=bind(connection)):
            pytest.fail("Must not enter generation")
    calls = connection.execute.await_args_list
    assert calls[-1].args[1] == {"key": locks.generation_lock_key("user", 1)}
    assert "pg_advisory_unlock" in str(calls[-1].args[0])
    assert all("pg_advisory_lock(" not in str(call.args[0]) for call in calls)
    connection.invalidate.assert_not_awaited()
    connection.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    "unlock-false", "owner-unlock-false", "unlock-error", "owner-unlock-error",
    "unlock-commit", "acquire-error", "slot-acquire-error", "acquire-commit",
])
async def test_uncertain_connection_is_invalidated_before_close(connection, failure):
    events = []
    connection.invalidate.side_effect = lambda: events.append("invalidate")
    connection.close.side_effect = lambda: events.append("close")
    error = OperationalError("lock", {}, Exception("database unavailable"))
    yes, no = Mock(scalar_one=lambda: True), Mock(scalar_one=lambda: False)
    if failure == "unlock-false":
        connection.execute.side_effect = [yes, yes, no, yes]
    elif failure == "owner-unlock-false":
        connection.execute.side_effect = [yes, yes, yes, no]
    elif failure == "unlock-error":
        connection.execute.side_effect = [yes, yes, error]
    elif failure == "owner-unlock-error":
        connection.execute.side_effect = [yes, yes, yes, error]
    elif failure == "unlock-commit":
        connection.commit.side_effect = [None, error]
    elif failure == "acquire-error":
        connection.execute.side_effect = error
    elif failure == "slot-acquire-error":
        connection.execute.side_effect = [yes, error]
    else:
        connection.commit.side_effect = error
    if failure in {"acquire-error", "slot-acquire-error", "acquire-commit"}:
        with pytest.raises(locks.GenerationLockUnavailable):
            async with locks.generation_lock("user", 1, bind=bind(connection)):
                pytest.fail("Must not enter generation")
    else:
        async with locks.generation_lock("user", 1, bind=bind(connection)):
            pass
    assert events == ["invalidate", "close"]


@pytest.mark.asyncio
async def test_cancellation_releases_lock_even_if_cancelled_again_during_cleanup(connection):
    entered, releasing, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def execute(statement, params):
        if "pg_advisory_unlock" in str(statement):
            releasing.set()
            await finish.wait()
        return Mock(scalar_one=lambda: True)
    connection.execute.side_effect = execute

    async def generation():
        async with locks.generation_lock("guest", 1, bind=bind(connection)):
            entered.set()
            await asyncio.Event().wait()
    task = asyncio.create_task(generation())
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    await asyncio.wait_for(releasing.wait(), 2)
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    connection.close.assert_awaited_once()
    connection.invalidate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidated", [False, True])
async def test_connection_check_does_not_reconnect(connection, invalidated):
    connection.invalidated = invalidated
    connection.execute.side_effect = OperationalError("SELECT 1", {}, Exception("lost"))
    with pytest.raises(locks.GenerationLockUnavailable):
        await locks.GenerationLock(connection).check_connection()
    assert connection.execute.await_count == (0 if invalidated else 1)


@pytest.mark.asyncio
async def test_untranslated_driver_error_invalidates_without_more_sql(connection):
    connection.execute.side_effect = [
        Mock(scalar_one=lambda: True), Mock(scalar_one=lambda: True),
        RuntimeError("driver protocol failure"),
    ]
    with pytest.raises(locks.GenerationLockUnavailable):
        async with locks.generation_lock("user", 1, bind=bind(connection)) as lock:
            await lock.check_connection()
    assert connection.execute.await_count == 3  # No unlock on an unknown session.
    connection.invalidate.assert_awaited_once()
    connection.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,status", [
    (locks.GenerationAlreadyInProgress(), 409),
    (locks.GenerationCapacityExceeded(), 503),
    (locks.GenerationLockUnavailable(), 503),
])
async def test_lock_refusal_does_not_consume_limits(client, db, tmp_path, monkeypatch, failure, status):
    @asynccontextmanager
    async def unavailable(owner_type, owner_id):
        assert owner_type == "guest" and isinstance(owner_id, int)
        raise failure
        yield
    monkeypatch.setattr(images, "generation_lock", unavailable)
    provider = AsyncMock()
    monkeypatch.setattr(images, "generate_image", provider)
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == status
    if status == 409:
        assert response.json() == {"detail": "Image generation is already in progress."}
    elif isinstance(failure, locks.GenerationCapacityExceeded):
        assert response.json() == {"detail": "Server is busy. Please try again later."}
    images.check_generation_rate_limit.assert_not_awaited()
    images.reserve_generation_neurons.assert_not_awaited()
    provider.assert_not_awaited()
    assert not list(db.sync.scalars(select(UserRequest)))
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_detected_connection_loss_prevents_provider(client, monkeypatch):
    @asynccontextmanager
    async def lost(*args):
        yield SimpleNamespace(check_connection=AsyncMock(side_effect=locks.GenerationLockUnavailable()))
    monkeypatch.setattr(images, "generation_lock", lost)
    provider = AsyncMock()
    monkeypatch.setattr(images, "generate_image", provider)
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == 503
    provider.assert_not_awaited()
