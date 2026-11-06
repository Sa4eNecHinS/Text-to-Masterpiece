"""Configuration and fail-closed boundary tests without a live provider."""
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from backend.api import images
from backend.core.config import Settings
from backend.database.rate_limiting import RateLimitExceeded


@pytest.mark.parametrize("field", [
    "RATE_LIMIT_USER_CAPACITY", "RATE_LIMIT_USER_REFILL_SECONDS",
    "RATE_LIMIT_IP_CAPACITY", "RATE_LIMIT_IP_REFILL_PER_MINUTE",
])
@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "abc"])
def test_invalid_rate_limit_configuration(monkeypatch, field, value):
    monkeypatch.setenv(field, value)
    with pytest.raises(ValidationError, match=field):
        Settings(_env_file=None)


@pytest.mark.parametrize("field", ["RATE_LIMIT_USER_CAPACITY", "RATE_LIMIT_IP_CAPACITY"])
@pytest.mark.parametrize("value", ["0.5", "1000000"])
def test_capacity_must_fit_whole_tokens(monkeypatch, field, value):
    monkeypatch.setenv(field, value)
    with pytest.raises(ValidationError, match=field):
        Settings(_env_file=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("error,status", [
    (RateLimitExceeded(15), 429),
    (OperationalError("rate limiter", {}, Exception("unavailable")), 503),
])
async def test_rate_failure_prevents_neurons_and_provider(client, monkeypatch, provider, error, status):
    monkeypatch.setattr(images, "check_generation_rate_limit", AsyncMock(side_effect=error))
    requests = provider(lambda request: pytest.fail("Must not call provider"))
    response = await client.post("/Text-to-Masterpiece/generate", json={"prompt": "city"})
    assert response.status_code == status
    if status == 429:
        assert response.headers["retry-after"] == "15"
    images.reserve_generation_neurons.assert_not_awaited()
    assert not requests


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"prompt": " "}, {"prompt": "city", "model_id": "unknown"}])
async def test_invalid_input_never_consumes_tokens(client, body):
    response = await client.post("/Text-to-Masterpiece/generate", json=body)
    assert response.status_code in {400, 422}
    images.check_generation_rate_limit.assert_not_awaited()
    images.reserve_generation_neurons.assert_not_awaited()
