"""Tests for the API client."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.parking_angers.api import (
    ParkingAngersApi,
    ParkingAngersConnectionError,
    ParkingAngersRateLimitError,
    ParkingAngersResponseError,
    _parse_reset,
)
from custom_components.parking_angers.const import USER_AGENT

from .conftest import REALTIME_URL, REFERENCE_URL, load_fixture


@pytest.fixture
async def api(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> ParkingAngersApi:
    return ParkingAngersApi(async_get_clientsession(hass))


async def test_availability(
    api: ParkingAngersApi, aioclient_mock: AiohttpClientMocker, realtime: dict
) -> None:
    aioclient_mock.get(REALTIME_URL, json=realtime)
    result = await api.async_get_availability()
    assert len(result) == 19
    assert result["Republique"] == 13
    assert result["Chateau"] == 167
    assert api.last_availability_raw == realtime
    _, url, _, headers = aioclient_mock.mock_calls[0]
    assert url.query["limit"] == "100"
    assert headers["User-Agent"] == USER_AGENT


async def test_reference(
    api: ParkingAngersApi, aioclient_mock: AiohttpClientMocker, reference: dict
) -> None:
    aioclient_mock.get(REFERENCE_URL, json=reference)
    result = await api.async_get_reference()
    assert len(result) == 18
    assert result["49007-P-006"]["nom"] == "Parking du Ralliement"


async def test_reference_ignores_records_without_id(
    api: ParkingAngersApi, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        REFERENCE_URL,
        json={"total_count": 2, "results": [{"nom": "x"}, {"id": "A", "nom": "y"}]},
    )
    assert list(await api.async_get_reference()) == ["A"]


async def test_dirty_records(
    api: ParkingAngersApi, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        REALTIME_URL,
        json={
            "total_count": 6,
            "results": [
                {"nom": "Ok", "disponible": 3},
                {"disponible": 4},
                {"nom": "", "disponible": 4},
                {"nom": "Text", "disponible": "12"},
                {"nom": "Bool", "disponible": True},
                "garbage",
                {"nom": " Spaced ", "disponible": 0},
            ],
        },
    )
    assert await api.async_get_availability() == {"Ok": 3, "Spaced": 0}


async def test_total_count_warning(
    api: ParkingAngersApi,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    aioclient_mock.get(REALTIME_URL, json={"total_count": 150, "results": []})
    assert await api.async_get_availability() == {}
    assert "150 records" in caplog.text


async def test_deprecation_header_logged_once(
    api: ParkingAngersApi,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
    realtime: dict,
) -> None:
    aioclient_mock.get(
        REALTIME_URL,
        json=realtime,
        headers={"ODS-Explore-API-Deprecation": "2027-01-01"},
    )
    await api.async_get_availability()
    await api.async_get_availability()
    assert caplog.text.count("deprecation") == 1


@pytest.mark.parametrize(
    ("status", "fixture"), [(404, "error_404.json"), (400, "error_400.json")]
)
async def test_client_errors(
    api: ParkingAngersApi,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    fixture: str,
) -> None:
    body = load_fixture(fixture)
    aioclient_mock.get(REALTIME_URL, status=status, json=body)
    with pytest.raises(ParkingAngersResponseError, match=body["error_code"]):
        await api.async_get_availability()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"text": "<html>not json</html>"},
        {"json": ["unexpected"]},
        {"json": {"results": "nope"}},
    ],
)
async def test_invalid_payload(
    api: ParkingAngersApi, aioclient_mock: AiohttpClientMocker, kwargs: dict[str, Any]
) -> None:
    aioclient_mock.get(REALTIME_URL, **kwargs)
    with pytest.raises(ParkingAngersResponseError):
        await api.async_get_availability()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"exc": TimeoutError()},
        {"exc": aiohttp.ClientConnectionError()},
        {"status": 503, "text": "unavailable"},
    ],
)
async def test_connection_errors(
    api: ParkingAngersApi, aioclient_mock: AiohttpClientMocker, kwargs: dict[str, Any]
) -> None:
    aioclient_mock.get(REALTIME_URL, **kwargs)
    with pytest.raises(ParkingAngersConnectionError):
        await api.async_get_availability()


async def test_rate_limit(
    api: ParkingAngersApi, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        REALTIME_URL,
        status=429,
        json={"error_code": "TooManyRequests"},
        headers={"X-RateLimit-Reset": "2026-11-09T00:00:00+00:00"},
    )
    with pytest.raises(ParkingAngersRateLimitError) as err:
        await api.async_get_availability()
    assert err.value.retry_after == datetime(2026, 11, 9, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("1794182400", datetime(2026, 11, 9, tzinfo=UTC)),
        ("2026-11-09T00:00:00", datetime(2026, 11, 9, tzinfo=UTC)),
        ("2026-11-09T01:00:00+01:00", datetime(2026, 11, 9, tzinfo=UTC)),
        ("tomorrow", None),
    ],
)
def test_parse_reset(value: str | None, expected: datetime | None) -> None:
    assert _parse_reset(value) == expected
