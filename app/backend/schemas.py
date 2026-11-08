from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints
from typing import Annotated


class GenerateRequest(BaseModel):
    chat_id: UUID | None = None
    prompt: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    model_id: Annotated[str, StringConstraints(min_length=1, max_length=200)] = (
        "cloudflare/flux-1-schnell"
    )


class ModelPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_id: str
    name: str


class ChatSummary(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class GenerateResponse(BaseModel):
    chat_id: UUID
    image_url: str
    model_id: str
    model_name: str


class ChatHistoryEntry(BaseModel):
    id: int
    prompt: str
    image_url: str
    created_at: datetime
    model_id: str | None
    model_name: str | None


class UserRegistration(BaseModel):
    # Kept permissive for the current frontend, which still sends a user_id field.
    model_config = ConfigDict(extra="ignore")

    email: str
    password: str


class UserPublic(BaseModel):
    id: int
    email: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: int | None = None
