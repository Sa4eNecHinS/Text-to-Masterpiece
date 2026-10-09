import logging
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Guest, User, UserRequest
from backend.core.security import hash_password


logger = logging.getLogger("uvicorn.error")


def _as_uuid(guest_uuid: UUID | str) -> UUID:
    return guest_uuid if isinstance(guest_uuid, UUID) else UUID(guest_uuid)


async def add_guest(guest_uuid: UUID | str, session: AsyncSession) -> Guest:
    guest = Guest(guest_id=_as_uuid(guest_uuid))
    session.add(guest)
    try:
        await session.flush()
    except Exception:
        logger.exception("Failed to create guest %s", guest_uuid)
        raise
    return guest


async def get_guest_by_uuid(
    guest_uuid: UUID | str, session: AsyncSession
) -> Guest | None:
    try:
        normalized_uuid = _as_uuid(guest_uuid)
    except TypeError, ValueError, AttributeError:
        return None
    result = await session.execute(
        select(Guest).where(Guest.guest_id == normalized_uuid)
    )
    return result.scalar_one_or_none()


async def add_user(email: str, password: str, session: AsyncSession) -> User:
    user = User(email=email, password=await hash_password(password=password))
    session.add(user)
    try:
        await session.flush()
    except Exception:
        logger.exception("Failed to create user for email %s", email)
        raise
    return user


async def get_user_by_email(email: str, session: AsyncSession) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(user_id: int, session: AsyncSession) -> User | None:
    return await session.get(User, user_id)


async def add_prompt_and_image(
    *,
    prompt: str,
    image_url: str,
    session: AsyncSession,
    user_id: int | None = None,
    guest_id: int | None = None,
) -> UserRequest:
    if (user_id is None) == (guest_id is None):
        raise ValueError("Exactly one of user_id or guest_id must be supplied")

    request = UserRequest(
        user_id=user_id,
        guest_id=guest_id,
        prompt=prompt,
        image_url=image_url,
    )
    session.add(request)
    try:
        await session.flush()
    except Exception:
        logger.exception("Failed to save generated image request")
        raise
    return request


def _history_row(request: UserRequest) -> dict:
    return {
        "id": request.id,
        "prompt": request.prompt,
        "image_url": request.image_url,
        "created_at": request.created_at,
    }


async def get_user_chat_history(
    user_id: int,
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    result = await session.execute(
        select(UserRequest)
        .where(UserRequest.user_id == user_id)
        .order_by(UserRequest.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [_history_row(request) for request in result.scalars()]


async def get_guest_chat_history(
    guest_id: int,
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    result = await session.execute(
        select(UserRequest)
        .where(UserRequest.guest_id == guest_id)
        .order_by(UserRequest.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [_history_row(request) for request in result.scalars()]


async def merge_guest_requests_into_user(
    guest_id: int,
    user_id: int,
    session: AsyncSession,
    *,
    delete_guest: bool = True,
) -> int:
    result = await session.execute(
        update(UserRequest)
        .where(UserRequest.guest_id == guest_id)
        .values(user_id=user_id, guest_id=None)
    )
    moved_count = result.rowcount or 0

    if delete_guest:
        await session.execute(delete(Guest).where(Guest.id == guest_id))

    try:
        await session.flush()
    except Exception:
        logger.exception(
            "Failed to merge guest %s requests into user %s", guest_id, user_id
        )
        raise
    return moved_count
