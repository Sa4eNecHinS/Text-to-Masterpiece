"""Session-level generation locks on dedicated connections from the app pool.

Each active generation costs one extra pool connection. No transaction is kept
open between lock operations. A 64-bit digest has a tiny, nonzero collision risk.
"""
import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

import anyio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from backend.core.config import settings
from backend.database.session import engine

logger = logging.getLogger("uvicorn.error")
# PostgreSQL's two-int32 keys do not overlap the owner's one-int64 key space.
GLOBAL_GENERATION_NAMESPACE = 1487001


class GenerationAlreadyInProgress(Exception):
    pass


class GenerationCapacityExceeded(Exception):
    pass


class GenerationLockUnavailable(Exception):
    pass


def generation_lock_key(owner_type: Literal["user", "guest"], owner_id: int) -> int:
    if owner_type not in {"user", "guest"}:
        raise ValueError("Unknown generation owner type")
    digest = hashlib.sha256(f"t2m:generation:{owner_type}:{owner_id}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


class GenerationLock:
    def __init__(self, connection: AsyncConnection, slot: int | None = None):
        self._connection = connection
        self._usable = True
        self.slot = slot

    async def check_connection(self) -> None:
        """Fail closed before spending on AI; never reconnect a lost lock session."""
        connection = self._connection
        if not self._usable or connection.closed or connection.invalidated:
            self._usable = False
            raise GenerationLockUnavailable("Generation lock connection was lost")
        try:
            await connection.execute(text("SELECT 1"))
            await connection.commit()
        except Exception as error:
            # Some asyncpg transport/protocol failures escape SQLAlchemy's
            # exception translation. Treat all probe errors as an unsafe session.
            self._usable = False
            raise GenerationLockUnavailable("Generation lock connection was lost") from error


async def _release(
    connection: AsyncConnection, key: int, acquired: bool, slot: int | None, safe: bool
) -> None:
    try:
        if acquired:
            if connection.closed or connection.invalidated:
                safe = False
            if safe:
                # Reverse acquisition order: global slot first, owner second.
                unlocked = True
                if slot is not None:
                    result = await connection.execute(
                        text("SELECT pg_advisory_unlock(:namespace, :slot)"),
                        {"namespace": GLOBAL_GENERATION_NAMESPACE, "slot": slot},
                    )
                    unlocked = result.scalar_one() is True
                result = await connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": key}
                )
                unlocked = (result.scalar_one() is True) and unlocked
                await connection.commit()
                safe = unlocked
                if not unlocked:
                    logger.error("Generation advisory lock was not held during release")
    except BaseException:
        safe = False
        logger.exception("Failed to release generation advisory lock")
    finally:
        # Pool rollback alone does NOT release session-level advisory locks.
        try:
            if not safe:
                await connection.invalidate()
        finally:
            await connection.close()


async def _finish_release(
    connection: AsyncConnection, key: int, acquired: bool, slot: int | None, safe: bool
) -> None:
    # Shield both AnyIO scope cancellation and asyncio Task.cancel(). Do not
    # return a connection until cleanup is complete, even on request cancellation.
    with anyio.CancelScope(shield=True):
        task = asyncio.create_task(_release(connection, key, acquired, slot, safe))
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError


@asynccontextmanager
async def generation_lock(
    owner_type: Literal["user", "guest"], owner_id: int, *, bind: AsyncEngine | None = None
) -> AsyncIterator[GenerationLock]:
    key = generation_lock_key(owner_type, owner_id)
    connection = None
    acquired = safe = False
    slot = None
    lock = None
    try:
        try:
            connection = await (bind if bind is not None else engine).connect()
            result = await connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
            )
            acquired = result.scalar_one() is True
            if acquired:
                for candidate in range(1, settings.AI_MAX_CONCURRENT_GENERATIONS + 1):
                    result = await connection.execute(
                        text("SELECT pg_try_advisory_lock(:namespace, :slot)"),
                        {"namespace": GLOBAL_GENERATION_NAMESPACE, "slot": candidate},
                    )
                    if result.scalar_one() is True:
                        slot = candidate
                        break
            # Session-level locks survive COMMIT. End SQLAlchemy's autobegin
            # transaction before rate/budget checks and the HTTP request.
            await connection.commit()
            # Only known acquisition outcomes may be unlocked and pooled. An
            # interrupted probe/COMMIT may have acquired an unrecorded lock;
            # invalidate that session instead of returning it to the pool.
            safe = True
        except Exception as error:
            raise GenerationLockUnavailable("Generation lock is unavailable") from error
        if not acquired:
            raise GenerationAlreadyInProgress
        if slot is None:
            raise GenerationCapacityExceeded
        lock = GenerationLock(connection, slot)
        yield lock
    finally:
        if connection is not None:
            # Do not issue more SQL or risk reconnection on an uncertain session.
            if lock is not None and not lock._usable:
                safe = False
            await _finish_release(connection, key, acquired, slot, safe)
