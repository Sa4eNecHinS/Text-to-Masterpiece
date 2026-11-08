"""Chats reuse the existing schema; provider calls never include chat history."""
from datetime import datetime, timezone
from uuid import UUID, uuid7
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from backend.api import images
from backend.core.security import create_access_token
from backend.database.models import Chat, Guest, User, UserRequest
from backend.database.queries import merge_guest_requests_into_user

BASE = "/Text-to-Masterpiece"


def owner(db, client, authenticated):
    row = User(email="owner@example.com", password="unused") if authenticated else Guest(guest_id=uuid7())
    db.sync.add(row)
    db.sync.commit()
    client.cookies.set(
        "access_token" if authenticated else "guest_id",
        create_access_token({"sub": str(row.id)}) if authenticated else str(row.guest_id),
    )
    return {"user_id" if authenticated else "guest_id": row.id}


def good_provider(provider):
    return provider(lambda request: httpx.Response(200, json={
        "success": True, "result": {"image": "/9j/aW1hZ2U="},
    }))


@pytest.mark.asyncio
@pytest.mark.parametrize("authenticated", [False, True])
async def test_create_continue_and_new_chat(client, db, provider, authenticated):
    ownership = owner(db, client, authenticated)
    requests = good_provider(provider)
    first = await client.post(f"{BASE}/generate", json={"prompt": "First prompt"})
    assert first.status_code == 200, first.text
    chat_id = first.json()["chat_id"]
    assert UUID(chat_id).version == 7
    chat = db.sync.get(Chat, UUID(chat_id))
    assert getattr(chat, next(iter(ownership))) == next(iter(ownership.values()))
    old_time = datetime(2000, 1, 1, tzinfo=timezone.utc)
    chat.updated_at = old_time
    db.sync.commit()
    second = await client.post(f"{BASE}/generate", json={"prompt": "Second prompt", "chat_id": chat_id})
    assert second.status_code == 200, second.text
    assert second.json()["chat_id"] == chat_id
    db.sync.refresh(chat)
    assert chat.updated_at.replace(tzinfo=timezone.utc) > old_time
    rows = (await client.get(f"{BASE}/chats/{chat_id}")).json()
    assert [row["prompt"] for row in rows] == ["First prompt", "Second prompt"]
    sidebar = (await client.get(f"{BASE}/chats")).json()
    assert len(sidebar) == 1 and sidebar[0]["title"] == "First prompt"
    assert len(list(db.sync.scalars(select(Chat)))) == 1
    assert {str(row.chat_id) for row in db.sync.scalars(select(UserRequest))} == {chat_id}
    # New chat is created only on the next successful generation with no ID.
    third = await client.post(f"{BASE}/generate", json={"prompt": "Other chat"})
    assert third.status_code == 200 and third.json()["chat_id"] != chat_id
    assert len((await client.get(f"{BASE}/chats")).json()) == 2
    import json
    assert [json.loads(request.content) for request in requests] == [
        {"prompt": prompt, "steps": 4} for prompt in ["First prompt", "Second prompt", "Other chat"]
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("authenticated", [False, True])
@pytest.mark.parametrize("kind", ["foreign-user", "foreign-guest", "missing"])
async def test_chat_access_is_checked_before_limits(client, db, tmp_path, monkeypatch, authenticated, kind):
    owner(db, client, authenticated)
    chat_id = uuid7()
    if kind != "missing":
        other = User(email="other@example.com", password="unused") if kind == "foreign-user" else Guest(guest_id=uuid7())
        db.sync.add(other)
        db.sync.flush()
        db.sync.add(Chat(id=chat_id, **{"user_id" if kind == "foreign-user" else "guest_id": other.id}))
        db.sync.commit()
    provider = AsyncMock()
    monkeypatch.setattr(images, "generate_image", provider)
    response = await client.get(f"{BASE}/chats/{chat_id}")
    assert response.status_code == 404
    response = await client.post(f"{BASE}/generate", json={"prompt": "city", "chat_id": str(chat_id)})
    assert response.status_code == 404
    images.check_generation_rate_limit.assert_not_awaited()
    images.reserve_generation_neurons.assert_not_awaited()
    provider.assert_not_awaited()
    assert not list(tmp_path.iterdir())
    assert not list(db.sync.scalars(select(UserRequest)))
    assert (await client.get(f"{BASE}/chats")).json() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"prompt": "city", "chat_id": "invalid"}, {"prompt": "city", "chat_id": 1}])
async def test_invalid_chat_uuid(client, body):
    assert (await client.post(f"{BASE}/generate", json=body)).status_code == 422
    images.check_generation_rate_limit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["provider", "history", "commit"])
async def test_failure_creates_no_empty_chat(client, db, provider, monkeypatch, tmp_path, failure):
    if failure == "provider":
        provider(lambda request: httpx.Response(503, json={"success": False}))
    else:
        good_provider(provider)
        if failure == "history":
            monkeypatch.setattr(images, "add_prompt_and_image", AsyncMock(side_effect=RuntimeError("failed history")))
        else:
            async def commit():
                if db.commit.await_count == 1:
                    db.sync.commit()
                else:
                    raise RuntimeError("failed generation transaction")
            monkeypatch.setattr(db, "commit", AsyncMock(side_effect=commit))
    response = await client.post(f"{BASE}/generate", json={"prompt": "city"})
    assert response.status_code == (502 if failure == "provider" else 500)
    assert not list(db.sync.scalars(select(Chat)))
    assert not list(db.sync.scalars(select(UserRequest)))
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_failed_continuation_does_not_update_chat(client, db, provider):
    good_provider(provider)
    chat_id = (await client.post(f"{BASE}/generate", json={"prompt": "first"})).json()["chat_id"]
    before = (await client.get(f"{BASE}/chats")).json()
    provider(lambda request: httpx.Response(503, json={"success": False}))
    assert (await client.post(f"{BASE}/generate", json={"prompt": "failed", "chat_id": chat_id})).status_code == 502
    assert (await client.get(f"{BASE}/chats")).json() == before
    assert len((await client.get(f"{BASE}/chats/{chat_id}")).json()) == 1


@pytest.mark.asyncio
async def test_migrated_legacy_rows_pagination_and_stable_order(client, db):
    ownership = owner(db, client, False)
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    new = datetime(2021, 1, 1, tzinfo=timezone.utc)
    ids = [uuid7(), uuid7(), uuid7()]
    for index, chat_id in enumerate(ids):
        db.sync.add(Chat(id=chat_id, **ownership, created_at=old, updated_at=old if index == 0 else new))
    db.sync.flush()
    # Same timestamps intentionally exercise the ID tiebreakers, not row order.
    for prompt in ["Legacy first", "Legacy second"]:
        db.sync.add(UserRequest(**ownership, chat_id=ids[0], prompt=prompt, object_key="images/old.jpg", model_id=None, created_at=old))
    for index in (1, 2):
        db.sync.add(UserRequest(**ownership, chat_id=ids[index], prompt=f"Chat {index}", object_key="images/old.jpg", created_at=old))
    db.sync.commit()
    pages = [(await client.get(f"{BASE}/chats?limit=1&offset={index}")).json()[0] for index in range(3)]
    assert [row["id"] for row in pages] == [str(ids[2]), str(ids[1]), str(ids[0])]
    assert pages[-1]["title"] == "Legacy first"
    assert (await client.get(f"{BASE}/chats?limit=1&offset=3")).json() == []
    rows = (await client.get(f"{BASE}/chats/{ids[0]}")).json()
    assert [row["prompt"] for row in rows] == ["Legacy first", "Legacy second"]
    assert all(row["model_id"] is None and row["model_name"] is None for row in rows)
    for query in ["limit=0", "limit=101", "offset=-1"]:
        assert (await client.get(f"{BASE}/chats?{query}")).status_code == 422


@pytest.mark.asyncio
async def test_guest_merge_rolls_back_chats_and_generations_together(client, db, provider):
    good_provider(provider)
    chat_id = UUID((await client.post(f"{BASE}/generate", json={"prompt": "city"})).json()["chat_id"])
    guest_id = db.sync.get(Chat, chat_id).guest_id
    user = User(email="registered@example.com", password="unused")
    db.sync.add(user)
    db.sync.commit()
    await merge_guest_requests_into_user(guest_id, user.id, db)
    await db.rollback()  # Simulate a failure later in the registration transaction.
    db.sync.expire_all()
    assert db.sync.get(Chat, chat_id).guest_id == guest_id
    assert db.sync.scalars(select(UserRequest)).one().guest_id == guest_id
    assert db.sync.get(Guest, guest_id) is not None
