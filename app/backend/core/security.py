import os
from datetime import datetime, timedelta, timezone

import jwt

from .config import load_environment

load_environment()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required")
if not ALGORITHM:
    raise RuntimeError("ALGORITHM environment variable is required")


def create_access_token(
    user_data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    to_encode = user_data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=20))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


import bcrypt

async def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

async def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
