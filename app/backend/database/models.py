from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Identity, Index, Integer, Text, func
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
