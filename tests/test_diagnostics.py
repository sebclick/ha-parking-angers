"""Tests for the diagnostics."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion

from .conftest import set_realtime


@pytest.mark.freeze_time("2026-11-08 12:00:00+00:00")
async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    freezer: FrozenDateTimeFactory,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMocker,
    realtime: dict,
    snapshot: SnapshotAssertion,
) -> None:
    realtime["results"].append({"nom": "Nouveau", "disponible": 42})
    set_realtime(mock_api, json=realtime)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    result = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)
    assert result["unmapped"] == ["Nouveau"]
    assert result["parking_count"] == 20
    assert result == snapshot
