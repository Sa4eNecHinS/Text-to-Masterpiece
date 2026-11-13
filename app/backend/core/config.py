import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


def load_environment() -> None:
    load_dotenv(BACKEND_DIR / ".env")


load_environment()


# NUMERIC(12,2) is the storage boundary for the persisted counter.
NeuronAmount = Annotated[
    Decimal,
    Field(gt=0, allow_inf_nan=False, max_digits=12, decimal_places=2),
]


class ModelCostConfigurationError(RuntimeError):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", extra="ignore", validate_default=True,
        hide_input_in_errors=True,
    )

    # Empty by default: production stays closed until its browser origin is known.
    # NoDecode lets us support an explicitly empty env value as well as JSON [].
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def validate_cors_origins(cls, value):
        if isinstance(value, str):
            value = json.loads(value) if value.strip() else []
        if not isinstance(value, list):
            raise ValueError("CORS_ORIGINS must be a JSON array of exact HTTP(S) origins")
        origins = []
        for origin in value:
            if not isinstance(origin, str) or not origin or origin != origin.strip():
                raise ValueError("Each CORS origin must be a non-empty string without whitespace")
            try:
                parts = urlsplit(origin)
                canonical = str(HttpUrl(origin)).removesuffix("/")
            except ValueError as error:
                raise ValueError("Invalid HTTP(S) origin") from error
            if (
                parts.scheme not in {"http", "https"}
                or not parts.netloc
                or parts.path or parts.query or parts.fragment
                or parts.username is not None or parts.password is not None
                or "*" in origin or "\\" in origin
                or origin != canonical
            ):
                raise ValueError("Use a canonical exact HTTP(S) origin without path, credentials or wildcard")
            if origin not in origins:
                origins.append(origin)
        return origins

    CLOUDFLARE_ACCOUNT_ID: str | None = None
    CLOUDFLARE_API_TOKEN: str | None = None
    IMAGE_MODEL: str = "@cf/black-forest-labs/flux-1-schnell"
    B2_ENDPOINT: HttpUrl = "https://s3.us-east-005.backblazeb2.com"
    B2_REGION: str = "us-east-005"
    B2_BUCKET_NAME: str = "ttm-images"
    B2_KEY_ID: SecretStr | None = None
    B2_APPLICATION_KEY: SecretStr | None = None

    # Per-process pool: five lock connections + up to five SQL transactions
    # + three concurrent auth/history/models requests for one production worker.
    DB_POOL_SIZE: Annotated[int, Field(gt=0)] = 7
    DB_MAX_OVERFLOW: Annotated[int, Field(ge=0)] = 6
    DB_POOL_TIMEOUT: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 10.0

    # Global slot numbers use PostgreSQL's two-int32 advisory-lock API.
    AI_MAX_CONCURRENT_GENERATIONS: Annotated[int, Field(gt=0, le=2**31 - 1)] = 5
    AI_DAILY_NEURON_LIMIT: NeuronAmount
    AI_NEURON_COST_FLUX_1_SCHNELL: NeuronAmount
    AI_NEURON_COST_FLUX_2_KLEIN_4B: NeuronAmount

    # Capacities are whole tokens and must fit NUMERIC(12,6).
    RATE_LIMIT_USER_CAPACITY: Annotated[int, Field(gt=0, le=999999)]
    RATE_LIMIT_USER_REFILL_SECONDS: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    RATE_LIMIT_IP_CAPACITY: Annotated[int, Field(gt=0, le=999999)]
    RATE_LIMIT_IP_REFILL_PER_MINUTE: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def validate_neuron_costs(self) -> "Settings":
        for field in (
            "AI_NEURON_COST_FLUX_1_SCHNELL",
            "AI_NEURON_COST_FLUX_2_KLEIN_4B",
        ):
            if getattr(self, field) > self.AI_DAILY_NEURON_LIMIT:
                raise ValueError(f"{field} must not exceed AI_DAILY_NEURON_LIMIT")
        return self


settings = Settings()


def neuron_cost(model_id: str) -> Decimal:
    # Prices only: model existence and provider IDs come from PostgreSQL.
    if model_id == "cloudflare/flux-1-schnell":
        return settings.AI_NEURON_COST_FLUX_1_SCHNELL
    if model_id == "cloudflare/flux-2-klein-4b":
        return settings.AI_NEURON_COST_FLUX_2_KLEIN_4B
    raise ModelCostConfigurationError(
        "AI neuron cost is not configured for the selected model."
    )


COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() in {
    "1", "true", "yes", "on"
}
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").lower()
if COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise RuntimeError("COOKIE_SAMESITE must be one of: lax, strict, none")
if COOKIE_SAMESITE == "none" and not COOKIE_SECURE:
    raise RuntimeError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")


def cloudflare_credentials() -> tuple[str, str]:
    if not settings.CLOUDFLARE_ACCOUNT_ID or not settings.CLOUDFLARE_API_TOKEN:
        raise RuntimeError(
            "Cloudflare image generation is not configured. Set "
            "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN in app/backend/.env."
        )
    return settings.CLOUDFLARE_ACCOUNT_ID, settings.CLOUDFLARE_API_TOKEN
