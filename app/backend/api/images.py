import logging
from decimal import Decimal
from typing import Annotated

from backend.api.dependencies import (
    check_generation_rate_limit,
    get_optional_current_user,
    get_or_create_guest,
)
from backend.core.config import (
    IMAGE_STORAGE_PATH,
    ModelCostConfigurationError,
    cloudflare_credentials,
    neuron_cost,
    settings,
)
from backend.database.ai_usage import DailyBudgetExceeded
from backend.database.dependencies import get_db
from backend.database.generation_lock import (
    GenerationAlreadyInProgress,
    GenerationCapacityExceeded,
    GenerationLock,
    GenerationLockUnavailable,
    generation_lock,
)
from backend.database.models import Guest, Model, User
from backend.database.rate_limiting import RateLimitExceeded
from backend.database.queries import (
    add_prompt_and_image,
    get_guest_by_uuid,
    get_guest_chat_history,
    get_model_by_id,
    get_models,
    get_user_chat_history,
)
from backend.schemas import (
    ChatHistoryEntry,
    GenerateRequest,
    GenerateResponse,
    ModelPublic,
)
from backend.services.ai_budget import reserve_generation_neurons
from backend.services.image_generation import (
    ImageGenerationError,
    generate_image,
    is_supported_model,
)
from backend.services.image_storage import delete_image, save_image
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
domain = "/Text-to-Masterpiece"
type DbSession = Annotated[AsyncSession, Depends(get_db)]
type OptionalUser = Annotated[User | None, Depends(get_optional_current_user)]
type GuestId = Annotated[str | None, Cookie(alias="guest_id")]
logger = logging.getLogger("uvicorn.error")


@router.get(f"{domain}/models", response_model=list[ModelPublic])
async def models(db: DbSession):
    return [
        model
        for model in await get_models(db)
        if is_supported_model(model.model_id, model.provider, model.provider_model_id)
    ]


@router.get(f"{domain}/chat_history", response_model=list[ChatHistoryEntry])
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
    model = await get_model_by_id(data.model_id, db)
    if model is None:
        raise HTTPException(status_code=400, detail="Unknown image generation model.")
    if not is_supported_model(model.model_id, model.provider, model.provider_model_id):
        raise HTTPException(
            status_code=400, detail="Unsupported image generation model."
        )

    try:
        cost = neuron_cost(model.model_id)
    except ModelCostConfigurationError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    try:
        account_id, api_token = cloudflare_credentials()
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    if request.client is None:
        raise HTTPException(status_code=503, detail="Unable to determine client IP.")

    # Resolve a verified owner before the lock or any token consumption. Stage
    # a new guest cookie until its identity is committed. Also end the catalogue
    # / authentication transaction before holding a pool connection for AI.
    guest_response = Response()
    try:
        guest = (
            await get_or_create_guest(guest_uuid, guest_response, db)
            if current_user is None else None
        )
        await db.commit()
    except SQLAlchemyError as error:
        await db.rollback()
        logger.exception("Failed to resolve generation owner")
        raise HTTPException(
            status_code=503, detail="Generation owner verification is unavailable."
        ) from error
    response.raw_headers.extend(
        (key, value) for key, value in guest_response.raw_headers if key == b"set-cookie"
    )
    error_headers = (
        {"Set-Cookie": response.headers["set-cookie"]}
        if "set-cookie" in response.headers else None
    )
    owner_type = "user" if current_user is not None else "guest"
    owner_id = current_user.id if current_user is not None else guest.id
    try:
        async with generation_lock(owner_type, owner_id) as lock:
            return await _generate_locked(
                data, request, response, db, current_user, guest, model,
                cost, account_id, api_token, error_headers, lock,
            )
    except GenerationAlreadyInProgress as error:
        raise HTTPException(
            status_code=409, detail="Image generation is already in progress.",
            headers=error_headers,
        ) from error
    except GenerationCapacityExceeded as error:
        raise HTTPException(
            status_code=503, detail="Server is busy. Please try again later.",
            headers=error_headers,
        ) from error
    except GenerationLockUnavailable as error:
        logger.exception("Generation lock is unavailable")
        raise HTTPException(
            status_code=503, detail="Generation locking is unavailable.",
            headers=error_headers,
        ) from error


async def _generate_locked(
    data: GenerateRequest,
    request: Request,
    response: Response,
    db: AsyncSession,
    current_user: User | None,
    guest: Guest | None,
    model: Model,
    cost: Decimal,
    account_id: str,
    api_token: str,
    error_headers: dict[str, str] | None,
    lock: GenerationLock,
) -> GenerateResponse:
    try:
        await check_generation_rate_limit(
            request.client.host,
            current_user.id if current_user is not None else None,
            str(guest.guest_id) if guest is not None else None,
            response,
        )
    except RateLimitExceeded as error:
        raise HTTPException(
            status_code=429, detail=str(error),
            headers={**(error_headers or {}), "Retry-After": str(error.retry_after)},
        ) from error
    except SQLAlchemyError as error:
        logger.exception("Failed to check generation rate limit")
        raise HTTPException(
            status_code=503, detail="Generation rate limiter is unavailable.",
            headers=error_headers,
        ) from error
    try:
        await reserve_generation_neurons(cost, settings.AI_DAILY_NEURON_LIMIT)
    except DailyBudgetExceeded as error:
        raise HTTPException(
            status_code=429, detail="Daily AI generation limit reached.",
            headers=error_headers,
        ) from error
    except SQLAlchemyError as error:
        logger.exception("Failed to reserve daily AI budget")
        raise HTTPException(
            status_code=503, detail="AI budget reservation is unavailable.",
            headers=error_headers,
        ) from error

    # Detect a lost lock session before starting the expensive HTTP operation.
    await lock.check_connection()
    # No automatic retries: each future provider attempt must reserve anew.
    try:
        image = await generate_image(
            prompt=data.prompt,
            account_id=account_id,
            api_token=api_token,
            model=model.provider_model_id,
        )
    except (ImageGenerationError, RuntimeError) as error:
        detail = str(error)
        raise HTTPException(status_code=502, detail=detail, headers=error_headers) from error

    try:
        image_path = await save_image(image, IMAGE_STORAGE_PATH)
    except OSError as error:
        logger.exception("Failed to store generated image")
        raise HTTPException(
            status_code=500, detail="Failed to store generated image", headers=error_headers
        ) from error

    image_url = str(request.url_for("images", path=image_path.name))
    try:
        if current_user is not None:
            await add_prompt_and_image(
                user_id=current_user.id,
                prompt=data.prompt,
                image_url=image_url,
                model_id=model.model_id,
                session=db,
            )
        else:
            await add_prompt_and_image(
                guest_id=guest.id,
                prompt=data.prompt,
                image_url=image_url,
                model_id=model.model_id,
                session=db,
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
            status_code=500, detail="Failed to save generated image", headers=error_headers
        ) from error
    return GenerateResponse(
        image_url=image_url, model_id=model.model_id, model_name=model.name
    )
