import logging, os
from datetime import timedelta
from typing import Annotated
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from backend.api.dependencies import get_current_user
from backend.core.config import COOKIE_SECURE, COOKIE_SAMESITE
from backend.core.security import create_access_token, verify_password
from backend.database.models import User
from backend.database.queries import (
    add_user,
    get_guest_by_uuid,
    get_user_by_email,
    merge_guest_requests_into_user,
)
from backend.database.dependencies import get_db
from backend.schemas import UserPublic, UserRegistration


logger = logging.getLogger("uvicorn.error")
auth_router = APIRouter(prefix="/auth", tags=["Auth"])
domain = "/Text-to-Masterpiece"
type db_session = Annotated[AsyncSession, Depends(get_db)]
type GuestId = Annotated[str | None, Cookie(alias="guest_id")]


def _token_expiry() -> timedelta:
    raw_value = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "20")
    try:
        minutes = int(raw_value)
    except ValueError as error:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be an integer") from error
    if minutes <= 0:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be positive")
    return timedelta(minutes=minutes)


def _set_access_token_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
        max_age=int(_token_expiry().total_seconds()),
    )


def _clear_guest_cookie(response: Response) -> None:
    response.delete_cookie(
        key="guest_id",
        path="/",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )


async def authenticate_user(
    email: str, password: str, session: AsyncSession
) -> User | None:
    user = await get_user_by_email(email=email, session=session)
    if user is None or not await verify_password(password, user.password):
        return None
    return user


@auth_router.post(f"{domain}/registrate")
async def registrate(
    user_data: UserRegistration,
    session: db_session,
    response: Response,
    guest_uuid: GuestId = None,
):
    try:
        async with session.begin():
            if await get_user_by_email(user_data.email, session) is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A user with this email already exists",
                )

            user = await add_user(
                email=user_data.email,
                password=user_data.password,
                session=session,
            )

            guest = await get_guest_by_uuid(guest_uuid, session) if guest_uuid else None
            if guest is not None:
                await merge_guest_requests_into_user(
                    guest_id=guest.id,
                    user_id=user.id,
                    session=session,
                )
    except IntegrityError as error:
        logger.exception("Registration failed for email %s", user_data.email)
        if getattr(error.orig, "sqlstate", None) == "23505":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists",
            ) from error
        raise

    access_token = create_access_token(
        user_data={"sub": str(user.id)},
        expires_delta=_token_expiry(),
    )
    _set_access_token_cookie(response, access_token)
    if guest_uuid is not None:
        _clear_guest_cookie(response)

    return {
        "message": "Registration successful",
        "user": UserPublic(id=user.id, email=user.email),
    }


@auth_router.post(f"{domain}/token")
async def login(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: db_session,
    guest_uuid: GuestId = None,
):
    async with session.begin():
        user = await authenticate_user(
            email=form_data.username,
            password=form_data.password,
            session=session,
        )
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )

        guest = await get_guest_by_uuid(guest_uuid, session) if guest_uuid else None
        if guest is not None:
            await merge_guest_requests_into_user(
                guest_id=guest.id,
                user_id=user.id,
                session=session,
            )

    access_token = create_access_token(
        user_data={"sub": str(user.id)},
        expires_delta=_token_expiry(),
    )
    _set_access_token_cookie(response, access_token)
    if guest_uuid is not None:
        _clear_guest_cookie(response)

    return {
        "message": "Login successful",
        "user": UserPublic(id=user.id, email=user.email),
    }


@auth_router.get(f"{domain}/users/me", response_model=UserPublic)
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserPublic:
    return UserPublic(id=current_user.id, email=current_user.email)
