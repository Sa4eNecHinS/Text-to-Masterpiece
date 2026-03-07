from typing import Annotated
from pydantic import BaseModel

from fastapi import Cookie


class GenerateRequest(BaseModel):
    prompt: str


class UserRegistration(BaseModel):
    user_id: Annotated[str | None, Cookie(alias="user_id")] = None
    token: Annotated[str, Cookie(alias="access_token")] = None
    email: str
    password: str
