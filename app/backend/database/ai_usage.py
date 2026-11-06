"""Atomic reservation of estimated Neurons, shared by all backend workers."""
from decimal import Decimal

from sqlalchemy import Date, Numeric, bindparam, cast, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import AIDailyUsage


class DailyBudgetExceeded(Exception):
    pass


def _utc_usage_date():
    # Use the statement's date, not the process clock or connection timezone.
    return cast(func.timezone("UTC", func.statement_timestamp()), Date)


async def reserve_daily_neurons(
    session: AsyncSession, cost: Decimal, daily_limit: Decimal
) -> Decimal:
    """Reserve in one statement; the caller owns commit/rollback.

    ON CONFLICT locks the day's row and checks its latest value, including
    reservations committed by concurrent transactions. No provider I/O here.
    """
    if (
        not cost.is_finite() or cost <= 0
        or not daily_limit.is_finite() or daily_limit <= 0
    ):
        raise ValueError("Neuron cost and daily limit must be positive finite Decimals")

    cost_param = bindparam("cost", type_=Numeric(12, 2))
    limit_param = bindparam("daily_limit", type_=Numeric(12, 2))
    statement = insert(AIDailyUsage.__table__).from_select(
        ["usage_date", "used_neurons"],
        select(_utc_usage_date(), cost_param).where(cost_param <= limit_param),
    )
    total = AIDailyUsage.used_neurons + statement.excluded.used_neurons
    statement = statement.on_conflict_do_update(
        index_elements=[AIDailyUsage.usage_date],
        set_={"used_neurons": total},
        where=total <= limit_param,
    ).returning(AIDailyUsage.used_neurons)

    result = await session.execute(
        statement, {"cost": cost, "daily_limit": daily_limit}
    )
    used = result.scalar_one_or_none()
    if used is None:
        raise DailyBudgetExceeded("Daily AI generation limit reached.")
    return used
