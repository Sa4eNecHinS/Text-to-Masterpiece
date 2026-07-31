import logging

from fastapi import APIRouter, Response, Request, Cookie, Depends
from uuid import uuid7
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession


from backend.database.db_queries import (
    add_user,
    add_prompt_and_image,
    update_user_email_and_password,
)
from backend.database.dependencies import get_db
from backend.api.api import llm_generation
from backend.pydantic_classes.models import GenerateRequest


logging.basicConfig(
    level=logging.INFO,
    format="[%(filename)s:%(lineno)d] - %(levelname)s - %(message)s",
)
logger = logging.getLogger("uvicorn.error")


router = APIRouter()
type UserId = Annotated[str | None, Cookie(alias="user_id")]
type db_session = Annotated[AsyncSession, Depends(get_db)]


cool_domain = "/Text-to-Masterpiece"


@router.get(f"{cool_domain}")
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
            secure=True,  # True - куки не будет предеоваться по HTTP, а будет по HTTP
            # False - куки передается по всем протоколам
        )

        # подводный камень в том, что пока куки не очищаются
        # и код после if не проходит

    return {"ok": True}


@router.post(f"{cool_domain}/generate")
async def generation(
    data: GenerateRequest,
    db: db_session,
    user_id: UserId,
):
    logger.info(f"user_id from cookie: {user_id}")

    prompt = data.prompt
    # img_url = await llm_generation(prompt=prompt, user_id=user_id)
    plug_img_url = "https://picsum.photos/512/512"  # заглушка
    await add_prompt_and_image(
        user_id=user_id,
        prompt="cao cao cao",
        image_url=plug_img_url,
        session=db,
    )

    return {"image_url": plug_img_url}


@router.get(f"{cool_domain}/about_me")
async def about_me():
    return {"github": "https://github.com/Sa4eNecHinS"}
