from datetime import datetime
from string import punctuation
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
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
    generation_id: int
    model_id: str
    model_name: str


class ChatHistoryEntry(BaseModel):
    id: int
    prompt: str
    created_at: datetime
    model_id: str | None
    model_name: str | None


class UserRegistration(BaseModel):
    # Kept permissive for the current frontend, which still sends a user_id field.
    model_config = ConfigDict(extra="ignore")

    email: str
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if (
            len(value) < 8
            or not any("A" <= char <= "Z" for char in value)
            or not any("0" <= char <= "9" for char in value)
            or not any(char in punctuation for char in value)
        ):
            raise ValueError(
                "Use at least 8 characters, including an uppercase letter (A-Z), "
                "a digit (0-9), and a special character (e.g. !@#$%)."
            )
        # bcrypt accepts at most 72 bytes; reject rather than truncate passwords.
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes.")
        return value


class UserPublic(BaseModel):
    id: int
    email: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: int | None = None
