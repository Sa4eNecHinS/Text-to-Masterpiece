from decimal import Decimal

from backend.database.models import RateLimitBucket
from sqlalchemy import Numeric, bindparam, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__("Too many generation requests. Please try again later.")


async def consume_bucket_token(
    session: AsyncSession,
    scope: str,
    subject_key: str,
    capacity: int,
    refill_tokens: Decimal,
    refill_seconds: Decimal,
) -> Decimal:
    """Atomically consume one token, or raise without changing the bucket.

    Caller must roll back the entire transaction on refusal. PostgreSQL locks
    the conflicting row and evaluates WHERE against its latest committed state.
    A read on refusal is only for Retry-After, never to authorize an UPDATE.
    """
    if scope not in {"ip", "user", "guest"}:
        raise ValueError("Invalid rate limit scope")
    if capacity < 1 or capacity > 999999:
        raise ValueError("Bucket capacity must be between 1 and 999999")
    if any(
        not value.is_finite() or value <= 0 for value in (refill_tokens, refill_seconds)
    ):
        raise ValueError("Refill values must be positive finite Decimals")

    bucket = RateLimitBucket.__table__
    now = func.statement_timestamp()
    elapsed = func.greatest(func.extract("epoch", now - bucket.c.updated_at), 0)
    refill = bindparam("refill_tokens", type_=Numeric())
    period = bindparam("refill_seconds", type_=Numeric())
    # Multiply before dividing to avoid rounding the refill rate in Python.
    available = func.least(capacity, bucket.c.tokens + elapsed * refill / period)
    statement = (
        insert(bucket)
        .values(
            scope=scope,
            subject_key=subject_key,
            tokens=Decimal(capacity - 1),
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=[bucket.c.scope, bucket.c.subject_key],
            set_={
                "tokens": available - 1,
                # A statement may have waited behind a newer timestamp's lock.
                "updated_at": func.greatest(bucket.c.updated_at, now),
            },
            where=available >= 1,
        )
        .returning(bucket.c.tokens)
    )
    parameters = {"refill_tokens": refill_tokens, "refill_seconds": refill_seconds}
    remaining = (await session.execute(statement, parameters)).scalar_one_or_none()
    if remaining is not None:
        return remaining

    # The refused UPSERT still holds the row lock until caller rollback, so
    # this diagnostic read observes the same bucket without a read/update race.
    retry = await session.scalar(
        select(func.ceil(func.greatest((1 - available) * period / refill, 0))).where(
            bucket.c.scope == scope, bucket.c.subject_key == subject_key
        ),
        parameters,
    )
    raise RateLimitExceeded(max(1, int(retry)))
