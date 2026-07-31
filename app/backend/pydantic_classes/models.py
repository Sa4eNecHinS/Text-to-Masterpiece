from typing import Annotated
from pydantic import BaseModel

from fastapi import Cookie


class GenerateRequest(BaseModel):
    prompt: str


class User(BaseModel):
    user_id: str | None = None
    email: str
    password: str


class Token(BaseModel):
    access_token: str | None = None
    token_type: str


class TokenData(BaseModel):
    user_id: str | None = None
