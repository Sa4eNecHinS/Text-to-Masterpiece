import os
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    CLOUDFLARE_ACCOUNT_ID: str | None = None
    CLOUDFLARE_API_TOKEN: str | None = None
    IMAGE_MODEL: str = "@cf/black-forest-labs/flux-1-schnell"
    IMAGE_STORAGE_DIR: str = "images"

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


IMAGE_STORAGE_PATH = Path(settings.IMAGE_STORAGE_DIR)
if not IMAGE_STORAGE_PATH.is_absolute():
    IMAGE_STORAGE_PATH = BACKEND_DIR / IMAGE_STORAGE_PATH
IMAGE_STORAGE_PATH = IMAGE_STORAGE_PATH.resolve()

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
