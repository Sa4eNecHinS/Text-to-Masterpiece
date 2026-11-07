"""Configuration and fail-closed API tests (no live PostgreSQL or Cloudflare)."""
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from backend.api import images
from backend.core.config import ModelCostConfigurationError, Settings, neuron_cost
from backend.database.ai_usage import DailyBudgetExceeded
from backend.database.models import Guest, UserRequest


@pytest.mark.parametrize("field", [
    "AI_DAILY_NEURON_LIMIT", "AI_NEURON_COST_FLUX_1_SCHNELL",
    "AI_NEURON_COST_FLUX_2_KLEIN_4B",
])
@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "-Infinity", "1.001", "abc", "10000000000"])
def test_invalid_neuron_settings(monkeypatch, field, value):
    monkeypatch.setenv(field, value)
    with pytest.raises(ValidationError, match=field):
        Settings(_env_file=None)


@pytest.mark.parametrize("field", ["AI_NEURON_COST_FLUX_1_SCHNELL", "AI_NEURON_COST_FLUX_2_KLEIN_4B"])
def test_cost_exceeds_limit(monkeypatch, field):
    monkeypatch.setenv(field, "9000.01")
    with pytest.raises(ValidationError, match=f"{field} must not exceed"):
        Settings(_env_file=None)


def test_decimal_settings_and_cost_mapping(monkeypatch):
    monkeypatch.setenv("AI_NEURON_COST_FLUX_1_SCHNELL", "65.25")
    config = Settings(_env_file=None)
    assert config.AI_NEURON_COST_FLUX_1_SCHNELL == Decimal("65.25")
    assert isinstance(config.AI_DAILY_NEURON_LIMIT, Decimal)
    assert neuron_cost("cloudflare/flux-1-schnell") == Decimal("65")
    assert neuron_cost("cloudflare/flux-2-klein-4b") == Decimal("110")
    with pytest.raises(ModelCostConfigurationError):
        neuron_cost("cloudflare/not-configured")


@pytest.mark.parametrize("field", [
    "AI_DAILY_NEURON_LIMIT", "AI_NEURON_COST_FLUX_1_SCHNELL",
    "AI_NEURON_COST_FLUX_2_KLEIN_4B",
])
def test_missing_settings_are_startup_errors(monkeypatch, field):
    monkeypatch.delenv(field)
    with pytest.raises(ValidationError, match=field):
        Settings(_env_file=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,status", [
    (DailyBudgetExceeded(), 429),
    (OperationalError("reserve", {}, Exception("database unavailable")), 503),
])
async def test_reservation_failure_never_calls_provider(client, db, provider, tmp_path, monkeypatch, failure, status):
    reserve = AsyncMock(side_effect=failure)
    monkeypatch.setattr(images, "reserve_generation_neurons", reserve)
    requests = provider(lambda request: pytest.fail("Provider must not be called"))
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == status
    if status == 429:
        assert response.json()["detail"] == "Daily AI generation limit reached."
    reserve.assert_awaited_once_with(Decimal("65"), Decimal("9000"))
    assert not requests
    assert not list(tmp_path.iterdir())
    assert not list(db.sync.scalars(select(UserRequest)))
    assert len(list(db.sync.scalars(select(Guest)))) == 1
    assert client.cookies.get("guest_id")


@pytest.mark.asyncio
async def test_missing_model_cost_is_server_error(client, provider, monkeypatch):
    # Only the server's cost resolver is trusted.
    def missing_cost(model_id):
        assert model_id == "cloudflare/flux-1-schnell"
        raise ModelCostConfigurationError("AI neuron cost is not configured for the selected model.")
    monkeypatch.setattr(images, "neuron_cost", missing_cost)
    reserve = images.reserve_generation_neurons
    requests = provider(lambda request: pytest.fail("Provider must not be called"))
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city", "cost": "0"})
    assert response.status_code == 500
    assert "not configured" in response.json()["detail"]
    reserve.assert_not_awaited()
    assert not requests
