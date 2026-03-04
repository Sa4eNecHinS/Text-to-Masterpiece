import os
import asyncio
from dotenv import load_dotenv
from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


load_dotenv()

db_url = URL.create(
    drivername=os.getenv("DB_DRIVER", "postgresql+asyncpg"),
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASS"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", 5432)),  # порт должен быть числом
    database=os.getenv("DB_NAME"),
)
engine = create_async_engine(db_url, echo=False)
SessionLocal = async_sessionmaker(engine)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "tests"}

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(unique=True)
    email: Mapped[str] = mapped_column(nullable=True, unique=True)
    password: Mapped[str] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return (
            f"User(user_id={self.user_id}, email={self.email}, password={self.password}"
        )


class UserRequest(Base):
    __tablename__ = "user_requests"
    __table_args__ = {"schema": "tests"}

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("tests.users.user_id", ondelete="CASCADE"), index=True
    )
    prompt: Mapped[str] = mapped_column()
    image_url: Mapped[str] = mapped_column()

    # server_default создаст таблицу в postgres с полем DEFAULT CURRENT_TIMESTAMP
    create_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def __repr__(self) -> str:
        return f"UserRequest(user_id={self.user_id}, prompt={self.prompt}, image_url={self.image_url}"


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())
