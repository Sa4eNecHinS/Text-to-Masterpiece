import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .db_models import SessionLocal, User, UserRequest
from .hash import (
    hash_password,
)


logging.basicConfig(
    level=logging.INFO,
    format="[%(filename)s:%(lineno)d] - %(levelname)s - %(message)s",
)
logger = logging.getLogger("uvicorn.error")

"""
Добавить управление сессией во все функции 
"""


async def add_user(
    user_id: str, email: str = None, password: str = None, session: AsyncSession = None
):
    if session is None:
        async with SessionLocal() as session:
            return await _logic_add_user(
                user_id=user_id,
                email=email,
                password=password,
                session=session,
            )
    else:
        return await _logic_add_user(
            user_id=user_id,
            email=email,
            password=password,
            session=session,
        )


async def _logic_add_user(
    user_id: str, email: str, password: str, session: AsyncSession
):
    try:
        hashed_password = await hash_password(password=password)

        new_user = User(
            user_id=user_id,
            email=email,
            password=hashed_password,
        )

        session.add(new_user)
        await session.commit()

        logger.info(f"User with user_id - {user_id} succefully ADDED")

    except Exception as err:
        await session.rollback()
        logger.info(f"Error happend while ADDED user, with user_id - {user_id}\n{err}")


async def get_user(user_id: str, session: AsyncSession = None):
    if session is None:
        async with SessionLocal() as session:
            return await _logic_get_user(
                user_id=user_id,
                session=session,
            )
    else:
        return await _logic_get_user(
            user_id=user_id,
            session=session,
        )


async def _logic_get_user(user_id: str, session: AsyncSession) -> dict[str]:
    query = select(User).where(User.user_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()  # вернет None, если объект не найден

    if user:
        logger.info(f"GET user with user_id = {user_id}")
        return {
            "user_id": user.user_id,
            "email": user.email,
            "hashed_password": user.password,
        }
    else:
        logger.info(f"Error happend while GETTING user with user_id = {user_id}")
        return None


async def update_user_email_and_password(
    user_id: str, email: str = None, password: str = None, session: AsyncSession = None
):
    if session is None:
        async with SessionLocal() as session:
            return await _update_logic_user_email_and_password(
                user_id=user_id,
                email=email,
                password=password,
                session=session,
            )
    else:
        return await _update_logic_user_email_and_password(
            user_id=user_id,
            email=email,
            password=password,
            session=session,
        )


async def _update_logic_user_email_and_password(
    user_id: str, email: str, password: str, session: AsyncSession
):
    try:
        hash_pswrd = await hash_password(password)

        user = (
            update(User)
            .where(User.user_id == user_id)
            .values(email=email, password=hash_pswrd)
        )
        await session.execute(user)
        await session.commit()

        logger.info(f"UPDATE email and password for user_id - {user_id}")

    except Exception as err:
        await session.rollback()
        logger.info(
            f"Error happend while UPDATE email and password, with user_id - {user_id}\n{err}"
        )


async def add_prompt_and_image(
    user_id: str, prompt: str, image_url: str, session: AsyncSession = None
):
    if session is None:
        async with SessionLocal() as session:
            return await _logic_add_prompt_and_image(
                user_id=user_id,
                prompt=prompt,
                image_url=image_url,
                session=session,
            )
    else:
        return await _logic_add_prompt_and_image(
            user_id=user_id,
            prompt=prompt,
            image_url=image_url,
            session=session,
        )


async def _logic_add_prompt_and_image(
    user_id: str, prompt: str, image_url: str, session: AsyncSession
):
    try:
        # существует ли вообще такой пользователь в основной таблице
        # Это важно, так как user_requests ссылается на users
        user_check = await session.execute(select(User).where(User.user_id == user_id))
        if not user_check.scalar_one_or_none():
            logger.warning(
                f"User_id={user_id} not found in 'users' table. Cannot add prompt."
            )
            return 0

        new_request = UserRequest(user_id=user_id, prompt=prompt, image_url=image_url)

        session.add(new_request)

        await session.commit()

        logger.info(
            f"NEW prompt and image_url successfully SAVED for user_id={user_id}"
        )

        return 1

    except Exception as err:
        await session.rollback()
        logger.error(
            f"Error happened when try to save new prompt for user_id={user_id}.\nErr={err}"
        )
        return 0


async def del_user(user_id: str, session: AsyncSession = None):
    if session is None:
        async with SessionLocal() as sesion:
            return _logic_del_user(
                user_id=user_id,
                session=session,
            )
    else:
        return _logic_del_user(
            user_id=user_id,
            session=session,
        )


async def _logic_del_user(user_id: str, session: AsyncSession):
    """функция сущесвует на всякий случай"""
    async with session() as session:
        try:
            result = await session.execute(select(User).where(User.user_id == user_id))
            user = (
                result.scalar_one_or_none()
            )  # вызывается у объекта который возвращает execute()

            await session.delete(user)
            await session.commit()
            logger.info(f"User with {user_id} succefelly DELETED")

        except Exception as err:
            await session.rollback()
            logger.warning(
                f"Error why deleting user from bd. User_id={user_id}.\nErr={err}"
            )
