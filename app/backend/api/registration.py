import os
import logging
from datetime import timedelta  # for jwt token expiration
from typing import Annotated
from dotenv import load_dotenv

import jwt
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Cookie
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_401_UNAUTHORIZED

from backend.database.db_queries import get_user, add_user
from backend.database.dependencies import get_db
from backend.pydantic_classes.models import (
    User,
    Token,
    TokenData,
)
from backend.database.hash import verify_password
from backend.api.create_jwt import (
    create_access_token,
    SECRET_KEY,
    ALGORITHM,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="[%(filename)s:%(lineno)d] - %(levelname)s - %(message)s",
)
logger = logging.getLogger("uvicorn.error")
auth_router = APIRouter(prefix="/auth", tags=["Auth"])
domain = "/Text-to-Masterpiece"

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"/{domain}/auth/token",
)

type UserId = Annotated[str | None, Cookie(alias="user_id")]
type db_session = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    request: Request,
    session: db_session,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not valudate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")  # subject

        if user_id is None:
            raise credentials_exception

        token_data = TokenData(user_id=user_id)

    except jwt.InvalidTokenError:
        raise credentials_exception
    # аутенфикация
    user = await get_user(
        user_id=request.cookies.get("user_id"),
        session=session,
    )
    if not user:
        raise credentials_exception
    return User(
        user_id=user["user_id"],
        email=user["email"],
        password=user["hashed_password"],
    )


async def authenticate_user(
    user_id: str,
    password: str,
    session: db_session,
) -> bool | dict[str]:
    user = await get_user(
        user_id=user_id,
        session=session,
    )
    if not user:
        return False

    checked_password = await verify_password(
        plain_password=password,
        hashed_password=user["hashed_password"],
    )
    if not checked_password:
        return False

    return user


@auth_router.post(f"{domain}/registrate")
async def registrate(
    user_data: User,
    session: db_session,
    response: Response,
    request: Request,
):
    user_id = user_data.user_id or request.cookies.get("user_id")
    user_in_db = await get_user(user_id=user_id)

    if user_in_db:
        raise HTTPException(
            status_code=409,
            detail=f"user with user_id = {user_id} already logged in",
        )

    await add_user(
        user_id=user_id,
        email=user_data.email,
        password=user_data.password,
        session=session,
    )

    response.set_cookie(
        key="access_token",
        value=user_id,
        httponly=True,
        secure=True,  # для https, но у меня пока http
    )
    # возвращаю токен, чтобы пользователь не вводил
    # свои данные повторно после регистрации
    return {
        "message": "Registration successful, you are logged in",
    }


@auth_router.post(f"{domain}/token")
async def login(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: db_session,
    user_id: UserId = None,
):
    user = await authenticate_user(
        session=session, user_id=user_id, password=form_data.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
    access_token_expires = timedelta(minutes=expire_minutes)
    access_token = await create_access_token(
        user_data={"sub": user_id},
        expires_delta=access_token_expires,
    )

    return Token(access_token=access_token, token_type="bearer")


@auth_router.get(f"{domain}/users/me")
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user
