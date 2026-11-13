import logging
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from backend.api.dependencies import (
    check_generation_rate_limit,
    get_optional_current_user,
    get_or_create_guest,
)
from backend.core.config import (
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
    create_chat,
    get_chat_generations,
    get_chats,
    get_guest_by_uuid,
    get_guest_chat_history,
    get_model_by_id,
    get_models,
    get_owned_chat,
    get_owned_generation,
    get_user_chat_history,
    lock_guest_history,
    touch_chat,
)
from backend.schemas import (
    ChatHistoryEntry,
    ChatSummary,
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
from backend.services.image_storage import (
    ImageStorage, StoredImage, StorageError, StorageNotFound,
    finish_io, get_image_storage, image_format,
)
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
domain = "/Text-to-Masterpiece"
type DbSession = Annotated[AsyncSession, Depends(get_db)]
type OptionalUser = Annotated[User | None, Depends(get_optional_current_user)]
type GuestId = Annotated[str | None, Cookie(alias="guest_id")]
logger = logging.getLogger("uvicorn.error")
PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


def get_storage() -> ImageStorage:
    # FastAPI executes sync dependencies in its thread pool (including SDK init).
    try:
        return get_image_storage()
    except StorageError as error:
        raise HTTPException(status_code=503, detail="Image storage is unavailable.") from error


type Storage = Annotated[ImageStorage, Depends(get_storage)]


class _ImageResponse(StreamingResponse):
    def __init__(self, image: StoredImage):
        self.image = image
        headers = dict(PRIVATE_HEADERS)
        if image.content_length is not None:
            headers["Content-Length"] = str(image.content_length)
        super().__init__(image.chunks(), media_type=image.content_type, headers=headers)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Also covers a disconnect before the iterator's first read.
            try:
                await finish_io(self.image.close())
            except StorageError:
                logger.error("Failed to close image download stream")


async def owned_image_key(
    generation_id: int, db: DbSession, current_user: OptionalUser,
    guest_uuid: GuestId = None,
) -> str:
    guest = (
        await get_guest_by_uuid(guest_uuid, db)
        if current_user is None and guest_uuid else None
    )
    generation = None
    if current_user is not None or guest is not None:
        generation = await get_owned_generation(
            generation_id, db,
            user_id=current_user.id if current_user is not None else None,
            guest_id=guest.id if guest is not None else None,
        )
    if generation is None:
        raise HTTPException(status_code=404, detail="Image not found.", headers=PRIVATE_HEADERS)
    key = generation.object_key
    await db.commit()  # No DB transaction/connection is held during B2 streaming.
    return key


@router.get("/images/{generation_id}", response_class=StreamingResponse)
async def private_image(
    generation_id: int,
    key: Annotated[str, Depends(owned_image_key)],
    storage: Storage,
):
    try:
        image = await storage.download(key)
    except StorageNotFound as error:
        raise HTTPException(status_code=404, detail="Image not found.", headers=PRIVATE_HEADERS) from error
    except StorageError as error:
        logger.error("Failed to read image generation_id=%s", generation_id)
        raise HTTPException(status_code=503, detail="Image storage is unavailable.", headers=PRIVATE_HEADERS) from error
    return _ImageResponse(image)


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


@router.get(f"{domain}/chats", response_model=list[ChatSummary])
async def chats(
    db: DbSession,
    current_user: OptionalUser,
    guest_uuid: GuestId = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    if current_user is not None:
        return await get_chats(db, user_id=current_user.id, limit=limit, offset=offset)
    guest = await get_guest_by_uuid(guest_uuid, db) if guest_uuid else None
    return (
        [] if guest is None
        else await get_chats(db, guest_id=guest.id, limit=limit, offset=offset)
    )


@router.get(f"{domain}/chats/{{chat_id}}", response_model=list[ChatHistoryEntry])
async def chat_generations(
    chat_id: UUID,
    db: DbSession,
    current_user: OptionalUser,
    guest_uuid: GuestId = None,
):
    guest = (
        await get_guest_by_uuid(guest_uuid, db)
        if current_user is None and guest_uuid else None
    )
    if current_user is None and guest is None:
        raise HTTPException(status_code=404, detail="Chat not found.")
    owner = {
        "user_id": current_user.id if current_user is not None else None,
        "guest_id": guest.id if guest is not None else None,
    }
    if await get_owned_chat(chat_id, db, **owner) is None:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return await get_chat_generations(chat_id, db, **owner)


@router.post(f"{domain}/generate", response_model=GenerateResponse)
async def generation(
    data: GenerateRequest,
    request: Request,
    response: Response,
    db: DbSession,
    current_user: OptionalUser,
    storage: Storage,
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
        if data.chat_id is not None:
            chat = await get_owned_chat(
                data.chat_id, db,
                user_id=current_user.id if current_user is not None else None,
                guest_id=guest.id if guest is not None else None,
            )
            if chat is None:
                raise HTTPException(status_code=404, detail="Chat not found.")
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
                cost, account_id, api_token, error_headers, lock, storage,
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
    storage: ImageStorage,
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
        content_type, extension = image_format(image)
    except StorageError as error:
        raise HTTPException(status_code=502, detail=str(error), headers=error_headers) from error
    object_key = f"images/{uuid4()}.{extension}"
    await lock.check_connection()
    try:
        await storage.upload(object_key, image, content_type)
    except BaseException as error:
        # A failed response/cancel does not prove PUT failed on the server. Do
        # not delete a possibly pre-existing object (conditional-write conflict).
        logger.error("Unconfirmed image upload; inspect object_key=%s", object_key)
        if not isinstance(error, Exception):
            raise
        if not isinstance(error, StorageError):
            raise
        raise HTTPException(
            status_code=503, detail="Image storage is unavailable.", headers=error_headers,
        ) from error

    commit_started = False
    try:
        # Fail closed after PUT too. This is not a fence: the PostgreSQL
        # session can still be lost after this probe, including during COMMIT.
        await lock.check_connection()
        owner = {
            "user_id": current_user.id if current_user is not None else None,
            "guest_id": guest.id if guest is not None else None,
        }
        if guest is not None and await lock_guest_history(guest.id, db) is None:
            raise RuntimeError("Guest owner changed during generation")
        if data.chat_id is None:
            chat = await create_chat(db, **owner)
        else:
            # Recheck in the short persistence transaction: ownership may have
            # changed (e.g. guest sign-in) while the provider was running.
            chat = await get_owned_chat(data.chat_id, db, **owner, for_update=True)
            if chat is None:
                raise RuntimeError("Chat owner changed during generation")
        generation = await add_prompt_and_image(
            **owner, chat_id=chat.id, prompt=data.prompt,
            object_key=object_key, model_id=model.model_id, session=db,
        )
        await touch_chat(chat.id, db)
        commit_started = True
        await db.commit()
    except BaseException as error:
        # ROLLBACK after a lost COMMIT response does NOT prove non-commit.
        # Only a pre-COMMIT failure or a definitive server rejection is safe.
        sqlstate = getattr(getattr(error, "orig", None), "sqlstate", "") or ""
        rejected_commit = isinstance(error, DBAPIError) and sqlstate[:2] in {"23", "40"}
        await finish_io(_rollback_generation(db, storage, object_key, not commit_started or rejected_commit))
        if not isinstance(error, Exception) or isinstance(error, GenerationLockUnavailable):
            raise
        logger.error("Failed to persist generation; object_key=%s", object_key)
        raise HTTPException(
            status_code=500, detail="Failed to save generated image", headers=error_headers
        ) from error
    return GenerateResponse(
        chat_id=chat.id, generation_id=generation.id, model_id=model.model_id, model_name=model.name
    )


async def _rollback_generation(db, storage: ImageStorage, object_key: str, can_delete: bool) -> None:
    try:
        await db.rollback()
    except Exception:
        can_delete = False
        logger.error("Failed to confirm rollback; retain object_key=%s", object_key)
    if not can_delete:
        logger.error("Database outcome unknown; retain object_key=%s for reconciliation", object_key)
        return
    try:
        await storage.delete(object_key)
    except StorageError:
        logger.error("Compensation failed; orphan object_key=%s requires administrative cleanup", object_key)
