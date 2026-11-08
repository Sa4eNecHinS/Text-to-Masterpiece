import logging
from uuid import UUID, uuid7

from backend.core.security import hash_password
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Chat, Guest, Model, User, UserRequest

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


async def get_models(session: AsyncSession) -> list[Model]:
    result = await session.execute(select(Model).order_by(Model.model_id))
    return list(result.scalars())


async def get_model_by_id(model_id: str, session: AsyncSession) -> Model | None:
    return await session.get(Model, model_id)


async def add_prompt_and_image(
    *,
    prompt: str,
    image_url: str,
    session: AsyncSession,
    user_id: int | None = None,
    guest_id: int | None = None,
    model_id: str | None = None,
    chat_id: UUID | None = None,
) -> UserRequest:
    if (user_id is None) == (guest_id is None):
        raise ValueError("Exactly one of user_id or guest_id must be supplied")

    request = UserRequest(
        user_id=user_id,
        guest_id=guest_id,
        prompt=prompt,
        image_url=image_url,
        model_id=model_id,
        chat_id=chat_id,
    )
    session.add(request)
    try:
        await session.flush()
    except Exception:
        logger.exception("Failed to save generated image request")
        raise
    return request


def _owner_filter(model, user_id: int | None, guest_id: int | None):
    if (user_id is None) == (guest_id is None):
        raise ValueError("Exactly one owner must be supplied")
    return model.user_id == user_id if user_id is not None else model.guest_id == guest_id


async def get_owned_chat(
    chat_id: UUID, session: AsyncSession, *,
    user_id: int | None = None, guest_id: int | None = None,
    for_update: bool = False,
) -> Chat | None:
    query = select(Chat).where(Chat.id == chat_id, _owner_filter(Chat, user_id, guest_id))
    if for_update:
        query = query.with_for_update()
    return (await session.execute(query)).scalar_one_or_none()


async def create_chat(
    session: AsyncSession, *, user_id: int | None = None, guest_id: int | None = None,
) -> Chat:
    _owner_filter(Chat, user_id, guest_id)
    # Explicit UUIDv7 also works in isolated SQLite tests; the existing PostgreSQL
    # server default remains available to other writers. No schema changes.
    chat = Chat(id=uuid7(), user_id=user_id, guest_id=guest_id)
    session.add(chat)
    await session.flush()
    return chat


async def get_chats(
    session: AsyncSession, *, user_id: int | None = None, guest_id: int | None = None,
    limit: int = 50, offset: int = 0,
) -> list[dict]:
    first_prompt = (
        select(UserRequest.prompt)
        .where(UserRequest.chat_id == Chat.id, _owner_filter(UserRequest, user_id, guest_id))
        .order_by(UserRequest.created_at, UserRequest.id)
        .limit(1).correlate(Chat).scalar_subquery()
    )
    result = await session.execute(
        select(Chat, func.coalesce(first_prompt, "New chat"))
        .where(_owner_filter(Chat, user_id, guest_id))
        .order_by(Chat.updated_at.desc(), Chat.id.desc()).limit(limit).offset(offset)
    )
    return [
        {"id": chat.id, "title": title, "created_at": chat.created_at, "updated_at": chat.updated_at}
        for chat, title in result
    ]


async def get_chat_generations(
    chat_id: UUID, session: AsyncSession, *,
    user_id: int | None = None, guest_id: int | None = None,
) -> list[dict]:
    result = await session.execute(
        select(UserRequest, Model.name)
        .outerjoin(Model, UserRequest.model_id == Model.model_id)
        .where(UserRequest.chat_id == chat_id, _owner_filter(UserRequest, user_id, guest_id))
        .order_by(UserRequest.created_at, UserRequest.id)
    )
    return [_history_row(request, name) for request, name in result]


async def touch_chat(chat_id: UUID, session: AsyncSession) -> None:
    await session.execute(update(Chat).where(Chat.id == chat_id).values(updated_at=func.now()))


def _history_row(request: UserRequest, model_name: str | None) -> dict:
    return {
        "id": request.id,
        "prompt": request.prompt,
        "image_url": request.image_url,
        "created_at": request.created_at,
        "model_id": request.model_id,
        "model_name": model_name,
    }


async def get_user_chat_history(
    user_id: int,
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    result = await session.execute(
        select(UserRequest, Model.name)
        .outerjoin(Model, UserRequest.model_id == Model.model_id)
        .where(UserRequest.user_id == user_id)
        .order_by(UserRequest.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [_history_row(request, name) for request, name in result]


async def get_guest_chat_history(
    guest_id: int,
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    result = await session.execute(
        select(UserRequest, Model.name)
        .outerjoin(Model, UserRequest.model_id == Model.model_id)
        .where(UserRequest.guest_id == guest_id)
        .order_by(UserRequest.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [_history_row(request, name) for request, name in result]


async def merge_guest_requests_into_user(
    guest_id: int,
    user_id: int,
    session: AsyncSession,
    *,
    delete_guest: bool = True,
) -> int:
    # Callers own the transaction. Move chats before requests and delete the
    # guest last, otherwise the guest FK cascade would delete its chats/history.
    await session.execute(
        update(Chat).where(Chat.guest_id == guest_id).values(user_id=user_id, guest_id=None)
    )
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
