from typing import Annotated
from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from backend.api.dependencies import get_optional_current_user, get_or_create_guest
from backend.database.dependencies import get_db
from backend.database.models import User

router = APIRouter()
domain = "/Text-to-Masterpiece"
type DbSession = Annotated[AsyncSession, Depends(get_db)]
type OptionalUser = Annotated[User | None, Depends(get_optional_current_user)]
type GuestId = Annotated[str | None, Cookie(alias="guest_id")]


@router.get(domain)
async def home_page(
    response: Response,
    db: DbSession,
    current_user: OptionalUser,
    guest_uuid: GuestId = None,
):
    if current_user is not None:
        return {"ok": True}
    try:
        guest = await get_or_create_guest(guest_uuid, response, db)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {"ok": True, "guest_id": str(guest.guest_id)}


@router.get(f"{domain}/about_me")
async def about_me():
    return {"github": "https://github.com/Sa4eNecHinS"}
