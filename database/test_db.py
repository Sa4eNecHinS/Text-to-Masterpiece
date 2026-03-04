import pytest
import pytest_asyncio

from database.db_queries import (
    add_user,
    add_prompt_and_image,
    update_user_email_and_password,
    del_user,
)
from database.db_models import (
    SessionLocal,
    User,
    UserRequest,
)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


# fixture - функция, которая готови почву для теста.
# в данном случае создает объекты сессий и подготовадяют БД
@pytest_asyncio.fixture(scope="function")
async def test_engine():
    engine = create_async_engine(
        "postgresql+asyncpg://postgres:yeah_body@localhost/postgres"
    )

    yield engine  # передаю подключение к БД
    await engine.dispose()  # закрытие всех соединений в пуле


@pytest_asyncio.fixture
async def session(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False)
    async with async_session() as session:
        yield session  # передаю сессию в тест
        await session.rollback()  # после теста отказываю все назад


@pytest.mark.asyncio
async def test_user_lifecycle():
    user_id = "019ca86f-8086-733d-a321-7f7a893a4734"
    email = "hui_i"
    password = "yeah_body"

    await add_user(
        user_id=user_id,
        email=email,
        password=password,
    )

    # добавился ли пользователь
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.user_id == user_id))
        assert res.scalar_one_or_none() is not None

    # await del_user(user_id)

    # удалился ли пользователь
    # async with async_session() as session:
    #    res = await session.execute(select(User).where(User.user_id == user_id))
    # assert res.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_add_prompt_and_image(session):
    user_id = "019ca86f-8086-733d-a321-7f7a893a4734"
    prompt = "u read my mind"
    image_url = "https://cau-cau/9291"

    await add_prompt_and_image(
        user_id=user_id,
        prompt=prompt,
        image_url=image_url,
        session=session,
    )

    async with session as session:
        res = await session.execute(
            select(UserRequest).where(UserRequest.user_id == user_id)
        )
        requests = res.scalars().all()

        assert len(requests) > 0

        latest_request = requests[-1]
        assert latest_request.prompt == prompt
        assert latest_request.image_url == image_url

    # await del_user(user_id)


@pytest.mark.asyncio
async def test_update_logic_email_and_password(session):
    user_id = "019ca86f-8086-733d-a321-7f7a893a4734"
    # email = "skksks)@gmail.com"
    # password = "ioio"
    email = "hui_i"
    password = "yeah_body"

    await update_user_email_and_password(
        user_id=user_id,
        email=email,
        password=password,
        session=session,
    )

    async with session as session:
        res = await session.execute(select(User).where(User.user_id == user_id))
        user = res.scalar_one_or_none()

        assert user is not None, "User doesn't found in database"
        assert user.email == email, "Email doesn't update"
        assert user.password != password, "Password DoNT NEED TO BE OPEN"
