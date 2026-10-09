import os

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from . import models
from backend.core.config import load_environment

load_environment()

db_url = URL.create(
    drivername=os.getenv("DB_DRIVER", "postgresql+asyncpg"),
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASS"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", 5432)),
    database=os.getenv("DB_NAME"),
)
engine = create_async_engine(db_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
