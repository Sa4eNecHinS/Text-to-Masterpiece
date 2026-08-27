import logging
import os

from fastapi import APIRouter, Response, Request, Cookie, Depends
from uuid import uuid7
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv


from backend.database.db_queries import (
    add_user,
    add_prompt_and_image,
    update_user_email_and_password,
    get_chat_history,
)
from backend.database.dependencies import get_db
from backend.api.llm import llm_generation
from backend.pydantic_classes.models import GenerateRequest


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="[%(filename)s:%(lineno)d] - %(levelname)s - %(message)s",
)
logger = logging.getLogger("uvicorn.error")
router = APIRouter()
domain = "/Text-to-Masterpiece"

type UserId = Annotated[str | None, Cookie(alias="user_id")]
type db_session = Annotated[AsyncSession, Depends(get_db)]


@router.get(f"{domain}")
async def home_page(
    request: Request,
    response: Response,
    db: db_session,
):
    if "user_id" not in request.cookies:
        user_id = str(uuid7())

        response.set_cookie(
            key="user_id",
            value=user_id,
            httponly=False,  # позволяет JS доставать куки из document.cookie
            samesite="none",  # чтобы кука принималась с другого домена
            secure=True,  # True - куки не будет предеоваться по HTTPS, а будет по HTTP
            # False - куки передается по всем протоколам
        )

        # подводный камень в том, что пока куки не очищаются
        # и код после if не проходит

    return {"ok": True}


@router.get(f"{domain}/chat_history")
async def chat_history(
    user_id: UserId,
    db: db_session,
):
    logger.info(f"Get user_history for user_id={user_id}")
    chat_history = await get_chat_history(
        user_id=user_id,
        session=db,
    )

    return chat_history


@router.post(f"{domain}/generate")
async def generation(
    data: GenerateRequest,
    db: db_session,
    user_id: UserId,
):
    prompt = data.prompt
    # img_url = await llm_generation(prompt=prompt, user_id=user_id)
    plug_img_url = "https://picsum.photos/512/512"  # заглушка
    await add_prompt_and_image(
        user_id=user_id,
        prompt=prompt,
        image_url=plug_img_url,
        session=db,
    )

    return {"image_url": plug_img_url}


@router.get(f"{domain}/about_me")
async def about_me():
    return {"github": "https://github.com/Sa4eNecHinS"}
