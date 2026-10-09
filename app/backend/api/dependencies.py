import jwt
from typing import Annotated
from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import COOKIE_SAMESITE, COOKIE_SECURE
from backend.core.security import ALGORITHM, SECRET_KEY
from backend.database.dependencies import get_db
from backend.database.models import Guest, User
from backend.database.queries import add_guest, get_guest_by_uuid, get_user_by_id
from uuid import uuid7

DbSession = Annotated[AsyncSession, Depends(get_db)]
GuestCookie = Annotated[str | None, Cookie(alias="guest_id")]
AccessToken = Annotated[str | None, Cookie(alias="access_token")]


async def get_optional_current_user(
    session: DbSession, access_token: AccessToken = None
) -> User | None:
    if not access_token:
        return None
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except jwt.InvalidTokenError, KeyError, TypeError, ValueError:
        return None
    return await get_user_by_id(user_id, session)


async def get_current_user(
    user: Annotated[User | None, Depends(get_optional_current_user)],
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    return user


def set_guest_cookie(response: Response, guest: Guest) -> None:
    response.set_cookie(
        key="guest_id",
        value=str(guest.guest_id),
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )


async def get_or_create_guest(
    guest_uuid: str | None, response: Response, session: AsyncSession
) -> Guest:
    guest = await get_guest_by_uuid(guest_uuid, session) if guest_uuid else None
    if guest is None:
        guest = await add_guest(uuid7(), session)
        set_guest_cookie(response, guest)
    return guest
