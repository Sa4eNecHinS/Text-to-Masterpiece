import logging
from typing import Annotated
from uuid import uuid7

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.registration import (
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    get_optional_current_user,
)
from backend.database.db_models import Guest, User
from backend.database.db_queries import (
    add_guest,
    add_prompt_and_image,
    get_guest_by_uuid,
    get_guest_chat_history,
    get_user_chat_history,
)
from backend.database.dependencies import get_db
from backend.pydantic_classes.models import GenerateRequest


logger = logging.getLogger("uvicorn.error")
router = APIRouter()
domain = "/Text-to-Masterpiece"

type GuestId = Annotated[str | None, Cookie(alias="guest_id")]
type db_session = Annotated[AsyncSession, Depends(get_db)]
type OptionalUser = Annotated[User | None, Depends(get_optional_current_user)]


def _set_guest_cookie(response: Response, guest: Guest) -> None:
    response.set_cookie(
        key="guest_id",
        value=str(guest.guest_id),
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )


async def _get_or_create_guest(
    guest_uuid: str | None,
    response: Response,
    session: AsyncSession,
) -> Guest:
    guest = await get_guest_by_uuid(guest_uuid, session) if guest_uuid else None
    if guest is not None:
        return guest

    guest = await add_guest(uuid7(), session)
    _set_guest_cookie(response, guest)
    return guest


@router.get(f"{domain}")
async def home_page(
    response: Response,
    db: db_session,
    current_user: OptionalUser,
    guest_uuid: GuestId = None,
):
    if current_user is not None:
        return {"ok": True}

    try:
        guest = await _get_or_create_guest(guest_uuid, response, db)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {"ok": True, "guest_id": str(guest.guest_id)}


@router.get(f"{domain}/chat_history")
async def chat_history(
    db: db_session,
    current_user: OptionalUser,
    guest_uuid: GuestId = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    if current_user is not None:
        return await get_user_chat_history(
            current_user.id, db, limit=limit, offset=offset
        )

    guest = await get_guest_by_uuid(guest_uuid, db) if guest_uuid else None
    if guest is None:
        return []
    return await get_guest_chat_history(guest.id, db, limit=limit, offset=offset)


@router.post(f"{domain}/generate")
async def generation(
    data: GenerateRequest,
    response: Response,
    db: db_session,
    current_user: OptionalUser,
    guest_uuid: GuestId = None,
):
    # img_url = await llm_generation(prompt=data.prompt, user_id=...)
    image_url = "https://picsum.photos/512/512"

    try:
        if current_user is not None:
            await add_prompt_and_image(
                user_id=current_user.id,
                prompt=data.prompt,
                image_url=image_url,
                session=db,
            )
        else:
            guest = await _get_or_create_guest(guest_uuid, response, db)
            await add_prompt_and_image(
                guest_id=guest.id,
                prompt=data.prompt,
                image_url=image_url,
                session=db,
            )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Failed to persist generation")
        raise HTTPException(status_code=500, detail="Failed to save generation")

    return {"image_url": image_url}


@router.get(f"{domain}/about_me")
async def about_me():
    return {"github": "https://github.com/Sa4eNecHinS"}
