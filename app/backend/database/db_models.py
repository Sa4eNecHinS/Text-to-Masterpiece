import os
from datetime import datetime
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy import DateTime, ForeignKey, Identity, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

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


class Base(DeclarativeBase):
    pass


class Guest(Base):
    __tablename__ = "guests"
    __table_args__ = {"schema": "tests"}

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    guest_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "tests"}

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(nullable=False, unique=True)
    password: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserRequest(Base):
    __tablename__ = "users_requests"
    __table_args__ = {"schema": "tests"}

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("tests.users.id", ondelete="CASCADE"), nullable=True
    )
    guest_id: Mapped[int | None] = mapped_column(
        ForeignKey("tests.guests.id", ondelete="CASCADE"), nullable=True
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
