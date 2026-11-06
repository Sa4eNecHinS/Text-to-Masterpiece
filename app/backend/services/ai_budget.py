"""Short, independent transactions for estimated provider spending."""
from decimal import Decimal

from backend.database.ai_usage import reserve_daily_neurons
from backend.database.session import SessionLocal


async def reserve_generation_neurons(cost: Decimal, daily_limit: Decimal) -> Decimal:
    # Never share the request/history transaction. The row lock is released
    # by COMMIT before returning, hence before any Cloudflare request.
    async with SessionLocal() as session:
        async with session.begin():
            used = await reserve_daily_neurons(session, cost, daily_limit)
    # Charges are deliberately never refunded, including on provider failures.
    return used
