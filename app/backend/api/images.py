import logging
from typing import Annotated
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from backend.api.dependencies import get_optional_current_user, get_or_create_guest
from backend.database.dependencies import get_db
from backend.database.models import User
from backend.database.queries import (
    add_prompt_and_image,
    get_guest_by_uuid,
    get_guest_chat_history,
    get_user_chat_history,
)
from backend.core.config import IMAGE_STORAGE_PATH, cloudflare_credentials, settings
from backend.schemas import GenerateRequest, GenerateResponse
from backend.services.image_generation import ImageGenerationError, generate_image
from backend.services.image_storage import delete_image, save_image

router = APIRouter()
domain = "/Text-to-Masterpiece"
type DbSession = Annotated[AsyncSession, Depends(get_db)]
type OptionalUser = Annotated[User | None, Depends(get_optional_current_user)]
type GuestId = Annotated[str | None, Cookie(alias="guest_id")]
logger = logging.getLogger("uvicorn.error")


@router.get(f"{domain}/chat_history")
async def chat_history(
    db: DbSession,
    current_user: OptionalUser,
    guest_uuid: GuestId = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    if current_user is not None:
        return await get_user_chat_history(
            current_user.id, db, limit=limit, offset=offset
        )
    guest = await get_guest_by_uuid(guest_uuid, db) if guest_uuid else None
    return (
        []
        if guest is None
        else await get_guest_chat_history(guest.id, db, limit=limit, offset=offset)
    )


@router.post(f"{domain}/generate", response_model=GenerateResponse)
async def generation(
    data: GenerateRequest,
    request: Request,
    response: Response,
    db: DbSession,
    current_user: OptionalUser,
    guest_uuid: GuestId = None,
):
    try:
        account_id, api_token = cloudflare_credentials()
        image = await generate_image(
            prompt=data.prompt,
            account_id=account_id,
            api_token=api_token,
            model=settings.IMAGE_MODEL,
        )
    except (ImageGenerationError, RuntimeError) as error:
        detail = str(error) if isinstance(error, RuntimeError) else str(error)
        raise HTTPException(status_code=502, detail=detail) from error

    try:
        image_path = await save_image(image, IMAGE_STORAGE_PATH)
    except OSError as error:
        logger.exception("Failed to store generated image")
        raise HTTPException(
            status_code=500, detail="Failed to store generated image"
        ) from error

    image_url = str(request.url_for("images", path=image_path.name))
    try:
        if current_user is not None:
            await add_prompt_and_image(
                user_id=current_user.id,
                prompt=data.prompt,
                image_url=image_url,
                session=db,
            )
        else:
            guest = await get_or_create_guest(guest_uuid, response, db)
            await add_prompt_and_image(
                guest_id=guest.id, prompt=data.prompt, image_url=image_url, session=db
            )
        await db.commit()
    except Exception as error:
        await db.rollback()
        try:
            await delete_image(image_path)
        except OSError:
            logger.exception("Failed to remove image after database failure")
        logger.exception("Failed to persist generation")
        raise HTTPException(
            status_code=500, detail="Failed to save generated image"
        ) from error
    return GenerateResponse(image_url=image_url)
