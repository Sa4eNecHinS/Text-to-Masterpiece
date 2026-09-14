from pydantic import BaseModel, ConfigDict


class GenerateRequest(BaseModel):
    prompt: str


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
