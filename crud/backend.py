from backend.api.api import llm_generation
import asyncio
import backend.database.db_queries as db
import logging


# __name__ - имя текущего файла
logger = logging.getLogger(__name__)


async def guest_or_user(user_id: str) -> bool:
    user = db.users.get(user_id)

    if user:
        logger.info(f"User - {user_id} is authorized")
        return True
    else:
        logger.info(f"User - {user_id} is not authorized")
        return False


async def generation_page(prompt: str, user_id: str):
    """
    Данная функция больше показ для фронта как нужно сделать,
    поэтому принты тут как приблизительный вариант,
    в конце концов эта функция уйдет из бэка и пойдет во фронт
    """
    while True:
        print("Генерация изображения....")
        response = await llm_generation(prompt=prompt, user_id=user_id)

        if response:
            print("Отправление изображения....")
            break


async def del_data_for_guest(user_id: str) -> bool:
    timeout = 20
    await asyncio.sleep(timeout)

    removed = db.users.pop(user_id, None)
    if removed:
        logging.info("Guest data with {user_id} was deleted")
        return True
    else:
        logging.info(
            "Guest data with {user_id} was NOT deleted. Maybe user_id not found"
        )
        return False


async def registration(user_id: str):
    pass
