import jwt
from decimal import Decimal
from typing import Annotated
from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import COOKIE_SAMESITE, COOKIE_SECURE, settings
from backend.core.security import ALGORITHM, SECRET_KEY
from backend.database.dependencies import get_db
from backend.database.models import Guest, User
from backend.database.queries import add_guest, get_guest_by_uuid, get_user_by_id
from backend.database.rate_limiting import consume_bucket_token
from backend.database.session import SessionLocal
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


async def check_generation_rate_limit(
    ip_address: str,
    user_id: int | None,
    guest_uuid: str | None,
    response: Response,
) -> str | None:
    """Commit both buckets (IP first, owner second) before any AI spending.

    Guest identity uses the existing mechanism and is persisted in this same
    short transaction. Stage its cookie until COMMIT has succeeded.
    """
    guest_response = Response()
    resolved_guest_uuid = None
    async with SessionLocal() as session:
        async with session.begin():
            await consume_bucket_token(
                session, "ip", ip_address, settings.RATE_LIMIT_IP_CAPACITY,
                settings.RATE_LIMIT_IP_REFILL_PER_MINUTE, Decimal("60"),
            )
            if user_id is not None:
                scope, subject_key = "user", str(user_id)
            else:
                guest = await get_or_create_guest(guest_uuid, guest_response, session)
                resolved_guest_uuid = str(guest.guest_id)
                scope, subject_key = "guest", resolved_guest_uuid
            await consume_bucket_token(
                session, scope, subject_key, settings.RATE_LIMIT_USER_CAPACITY,
                Decimal("1"), settings.RATE_LIMIT_USER_REFILL_SECONDS,
            )
    response.raw_headers.extend(
        (key, value) for key, value in guest_response.raw_headers if key == b"set-cookie"
    )
    return resolved_guest_uuid
