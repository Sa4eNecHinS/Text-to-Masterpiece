import os

from backend.core.config import load_environment, settings
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

load_environment()

db_url = URL.create(
    drivername=os.getenv("DB_DRIVER", "postgresql+asyncpg"),
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASS"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", 5432)),
    database=os.getenv("DB_NAME"),
)
# A worker can hold every global slot. Keep five further pooled connections
# for owner resolution, rate/budget transactions and history, plus burst overflow.
engine = create_async_engine(
    db_url, echo=False,
    pool_size=settings.AI_MAX_CONCURRENT_GENERATIONS + 5,
    max_overflow=10,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
