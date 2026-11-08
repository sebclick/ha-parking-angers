"""Tests for the binary sensors."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.parking_angers.const import (
    CONF_FULL_THRESHOLD,
    CONF_PARKINGS,
    CONF_SCAN_INTERVAL,
)

from .conftest import set_realtime
from .test_sensor import state


async def test_full_default_threshold(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    # Ralliement: 12 / 432 free -> 97.2 %
    assert state(hass, "binary_sensor", "ralliement_full").state == STATE_ON
    # Mail: 148 / 960 free -> 84.6 %
    assert state(hass, "binary_sensor", "mail_full").state == STATE_OFF


@pytest.mark.parametrize(
    ("threshold", "expected"),
    [(74, STATE_ON), (75, STATE_ON), (76, STATE_OFF)],
)
async def test_full_around_threshold(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    threshold: int,
    expected: str,
) -> None:
    # Larrey: 7 / 28 free -> exactly 75 %
    set_realtime(
        mock_api,
        json={"total_count": 1, "results": [{"nom": "Larrey", "disponible": 7}]},
    )
    entry = MockConfigEntry(
        domain="parking_angers",
        data={},
        options={
            CONF_PARKINGS: ["Larrey"],
            CONF_SCAN_INTERVAL: 10,
            CONF_FULL_THRESHOLD: threshold,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert state(hass, "binary_sensor", "larrey_full").state == expected


async def test_stale_data(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
) -> None:
    stale = state(hass, "binary_sensor", "stale_data")
    assert stale.state == STATE_OFF
    assert stale.attributes["device_class"] == "problem"
    assert stale.attributes["last_change"] == dt_util.utcnow().isoformat()
    entry = er.async_get(hass).async_get(stale.entity_id)
    assert entry.entity_category is er.EntityCategory.DIAGNOSTIC

    freezer.tick(timedelta(hours=3))
    await init_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert state(hass, "binary_sensor", "stale_data").state == STATE_ON
    # Car park entities stay available with the last value.
    assert state(hass, "sensor", "ralliement_available_spaces").state == "12"
