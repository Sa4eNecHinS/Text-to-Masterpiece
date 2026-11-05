import httpx
import pytest
from sqlalchemy import select

from backend.database.models import Guest, UserRequest
from backend.database.queries import add_user


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["registrate", "token"])
async def test_guest_history_merge_and_session(client, db, provider, action):
    if action == "token":
        await add_user("user@example.com", "password123", db)
        await db.commit()
    assert (await client.get("/auth/Text-to-Masterpiece/users/me")).status_code == 401
    assert (await client.get("/Text-to-Masterpiece")).status_code == 200
    guest_id = client.cookies.get("guest_id")
    assert guest_id
    requests = provider(lambda request: httpx.Response(200, json={
        "success": True, "result": {"image": "aW1hZ2U="},
    }))
    for model_id in ["cloudflare/flux-1-schnell", "cloudflare/flux-2-klein-4b"]:
        response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city", "model_id": model_id})
        assert response.status_code == 200
    assert len(requests) == 2
    if action == "registrate":
        response = await client.post("/auth/Text-to-Masterpiece/registrate", json={
            "email": "user@example.com", "password": "password123",
        })
    else:
        response = await client.post("/auth/Text-to-Masterpiece/token", data={
            "username": "user@example.com", "password": "password123",
        })
    assert response.status_code == 200, response.text
    assert client.cookies.get("access_token") and not client.cookies.get("guest_id")
    user = (await client.get("/auth/Text-to-Masterpiece/users/me")).json()
    assert user["email"] == "user@example.com"
    rows = list(db.sync.scalars(select(UserRequest)))
    assert len(rows) == 2 and all(row.user_id == user["id"] and row.guest_id is None for row in rows)
    assert {row.model_id for row in rows} == {"cloudflare/flux-1-schnell", "cloudflare/flux-2-klein-4b"}
    assert not list(db.sync.scalars(select(Guest)))
    history = (await client.get("/Text-to-Masterpiece/chat_history")).json()
    assert len(history) == 2 and all(entry["model_name"] for entry in history)
    assert (await client.post("/auth/Text-to-Masterpiece/logout")).status_code == 200
    assert (await client.get("/auth/Text-to-Masterpiece/users/me")).status_code == 401
    assert (await client.get("/Text-to-Masterpiece/chat_history")).json() == []
