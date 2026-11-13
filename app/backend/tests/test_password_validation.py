import pytest
from pydantic import ValidationError
from sqlalchemy import select

from backend.database.models import User
from backend.schemas import UserRegistration
from backend.database.queries import add_user


INVALID_PASSWORDS = [
    "", "Abc1!xy", "abcdef1!", "Abcdefg!", "Abcdef12", "Abcdef1 ",
    "Abcdef1😀", "A1!" + "a" * 70, "A1!" + "я" * 35,
]
VALID_PASSWORDS = ["Abcdef1!", "ABCDEFG1_", "Abcdef1 !", "A1!" + "a" * 69, "A1!" + "я" * 34]


@pytest.mark.parametrize("password", INVALID_PASSWORDS)
def test_schema_rejects_invalid_password(password):
    with pytest.raises(ValidationError) as error:
        UserRegistration(email="user@example.com", password=password)
    assert error.value.errors()[0]["loc"] == ("password",)


@pytest.mark.parametrize("password", VALID_PASSWORDS)
def test_schema_preserves_valid_password(password):
    assert UserRegistration(email="user@example.com", password=password).password == password


@pytest.mark.asyncio
@pytest.mark.parametrize("password", INVALID_PASSWORDS)
async def test_registration_rejects_invalid_password_before_creating_user(client, db, password):
    response = await client.post("/auth/Text-to-Masterpiece/registrate", json={
        "email": "user@example.com", "password": password,
    })
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "password"]
    assert db.sync.scalar(select(User)) is None
    assert not client.cookies.get("access_token")


@pytest.mark.asyncio
async def test_valid_password_registers_and_logs_in(client):
    response = await client.post("/auth/Text-to-Masterpiece/registrate", json={
        "email": "user@example.com", "password": "Abcdef1!",
    })
    assert response.status_code == 200
    assert client.cookies.get("access_token")
    response = await client.post("/auth/Text-to-Masterpiece/token", data={
        "username": "user@example.com", "password": "Abcdef1!",
    })
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_existing_weak_password_still_logs_in(client, db):
    await add_user("legacy@example.com", "password123", db)
    await db.commit()
    response = await client.post("/auth/Text-to-Masterpiece/token", data={
        "username": "legacy@example.com", "password": "password123",
    })
    assert response.status_code == 200
