import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

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
