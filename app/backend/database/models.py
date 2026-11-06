from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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


class Model(Base):
    __tablename__ = "models"
    __table_args__ = {"schema": "tests"}

    model_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_model_id: Mapped[str] = mapped_column(Text, nullable=False)


class AIDailyUsage(Base):
    __tablename__ = "ai_daily_usage"
    __table_args__ = (
        CheckConstraint(
            "used_neurons >= 0",
            name="ck_ai_daily_usage_non_negative",
        ),
        {"schema": "tests"},
    )

    usage_date: Mapped[date] = mapped_column(
        Date,
        primary_key=True,
    )

    used_neurons: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0"),
    )


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"

    __table_args__ = (
        CheckConstraint(
            "tokens >= 0",
            name="ck_rate_limit_buckets_tokens_non_negative",
        ),
        CheckConstraint(
            "scope IN ('user', 'guest', 'ip')",
            name="ck_rate_limit_buckets_scope",
        ),
        {"schema": "tests"},
    )

    scope: Mapped[str] = mapped_column(
        String(16),
        primary_key=True,
    )

    subject_key: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )

    tokens: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
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
    __table_args__ = (
        CheckConstraint(
            "char_length(prompt) <= 2000",
            name="ck_users_requests_prompt_length",
        ),
        {"schema": "tests"},
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("tests.users.id", ondelete="CASCADE"), nullable=True
    )
    guest_id: Mapped[int | None] = mapped_column(
        ForeignKey("tests.guests.id", ondelete="CASCADE"), nullable=True
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("tests.models.model_id", name="fk_users_requests_model_id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


Index(
    "idx_user_requests_guest_history",
    UserRequest.guest_id,
    UserRequest.created_at.desc(),
)

Index(
    "idx_user_requests_user_history",
    UserRequest.user_id,
    UserRequest.created_at.desc(),
)
