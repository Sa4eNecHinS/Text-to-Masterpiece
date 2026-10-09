import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


def load_environment() -> None:
    load_dotenv(BACKEND_DIR / ".env")


load_environment()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    CLOUDFLARE_ACCOUNT_ID: str | None = None
    CLOUDFLARE_API_TOKEN: str | None = None
    IMAGE_MODEL: str = "@cf/black-forest-labs/flux-1-schnell"
    IMAGE_STORAGE_DIR: str = "images"


settings = Settings()
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
