"""Fixtures for the Parking Angers tests."""

from __future__ import annotations

from collections.abc import Generator
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.parking_angers.const import (
    API_BASE_URL,
    CONF_FULL_THRESHOLD,
    CONF_PARKINGS,
    CONF_SCAN_INTERVAL,
    DOMAIN,
    REALTIME_DATASET,
    REFERENCE_DATASET,
)

FIXTURES = Path(__file__).parent / "fixtures"
REALTIME_URL = f"{API_BASE_URL}/{REALTIME_DATASET}/records"
REFERENCE_URL = f"{API_BASE_URL}/{REFERENCE_DATASET}/records"


def load_fixture(name: str) -> Any:
    """Load a JSON fixture."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Enable custom integrations in all tests."""
    return


@pytest.fixture
def realtime() -> dict[str, Any]:
    """Real-time response."""
    return load_fixture("realtime.json")


@pytest.fixture
def reference() -> dict[str, Any]:
    """Reference response."""
    return load_fixture("reference.json")


@pytest.fixture
def mock_api(
    aioclient_mock: AiohttpClientMocker,
    realtime: dict[str, Any],
    reference: dict[str, Any],
) -> AiohttpClientMocker:
    """Mock both API endpoints with the captured responses."""
    aioclient_mock.get(REALTIME_URL, json=realtime)
    aioclient_mock.get(REFERENCE_URL, json=reference)
    return aioclient_mock


def set_realtime(aioclient_mock: AiohttpClientMocker, **kwargs: Any) -> None:
    """Replace the real-time mock while keeping the reference one."""
    aioclient_mock._mocks[:] = [
        mock for mock in aioclient_mock._mocks if REALTIME_DATASET not in str(mock._url)
    ]
    aioclient_mock.get(REALTIME_URL, **kwargs)


def set_reference(aioclient_mock: AiohttpClientMocker, **kwargs: Any) -> None:
    """Replace the reference mock while keeping the real-time one."""
    aioclient_mock._mocks[:] = [
        mock
        for mock in aioclient_mock._mocks
        if REFERENCE_DATASET not in str(mock._url)
    ]
    aioclient_mock.get(REFERENCE_URL, **kwargs)


OPTIONS = {
    CONF_PARKINGS: ["Ralliement", "Mail", "Chateau", "Saint Laud 2", "Confluences"],
    CONF_SCAN_INTERVAL: 10,
    CONF_FULL_THRESHOLD: 95,
}


@pytest.fixture
def options() -> dict[str, Any]:
    """Options of the config entry."""
    return dict(OPTIONS)


@pytest.fixture
def config_entry(hass: HomeAssistant, options: dict[str, Any]) -> MockConfigEntry:
    """A config entry added to hass."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Parking Angers", data={}, options=options
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AiohttpClientMocker
) -> MockConfigEntry:
    """Set up the integration."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


@pytest.fixture
def no_platforms() -> Generator[None]:
    """Set up the entry without platforms."""
    with patch("custom_components.parking_angers.PLATFORMS", []):
        yield
