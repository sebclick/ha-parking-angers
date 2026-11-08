"""Tests for the sensors."""

from __future__ import annotations

from homeassistant.const import ATTR_ATTRIBUTION, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.parking_angers.const import (
    CONF_FULL_THRESHOLD,
    CONF_PARKINGS,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.parking_angers.sensor import AvailableSpacesSensor

from .conftest import set_realtime, set_reference


def entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)


def state(hass: HomeAssistant, platform: str, unique_id: str):
    eid = entity_id(hass, platform, unique_id)
    assert eid is not None, unique_id
    return hass.states.get(eid)


async def test_values(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    available = state(hass, "sensor", "ralliement_available_spaces")
    assert available.state == "12"
    assert available.attributes["unit_of_measurement"] == "places"
    assert available.attributes["state_class"] == "measurement"
    assert "ALTER" in available.attributes[ATTR_ATTRIBUTION]
    assert available.entity_id == "sensor.parking_du_ralliement_free_spaces"

    occupancy = state(hass, "sensor", "ralliement_occupancy")
    assert float(occupancy.state) == pytest.approx((1 - 12 / 432) * 100)
    assert occupancy.attributes["unit_of_measurement"] == "%"

    capacity = state(hass, "sensor", "ralliement_capacity")
    assert capacity.state == "432"
    entry = er.async_get(hass).async_get(capacity.entity_id)
    assert entry.entity_category is er.EntityCategory.DIAGNOSTIC

    assert state(hass, "sensor", "chateau_capacity").state == "300"
    assert state(hass, "sensor", "saint_laud_2_available_spaces").state == "155"
    # Not selected: no entity.
    assert entity_id(hass, "sensor", "quai_available_spaces") is None


async def test_device(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, "Ralliement"), init_integration.entry_id
    )
    assert device.name == "Parking du Ralliement"
    assert device.manufacturer == "ALTER"
    assert device.model == "ouvrage"
    assert (
        device.configuration_url == "http://parking-angers.fr/parking-du-ralliement-2/"
    )
    assert device.entry_type is dr.DeviceEntryType.SERVICE


async def test_occupancy_clamped(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    # Confluences: 31 free spaces for a capacity of 30.
    assert state(hass, "sensor", "confluences_available_spaces").state == "31"
    assert float(state(hass, "sensor", "confluences_occupancy").state) == 0


async def test_attributes(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    attrs = state(hass, "sensor", "ralliement_available_spaces").attributes
    assert attrs["latitude"] == pytest.approx(47.4712242886)
    assert attrs["longitude"] == pytest.approx(-0.5518064832)
    assert attrs["address"] == "5 PLACE DU RALLIEMENT"
    assert attrs["url"] == "http://parking-angers.fr/parking-du-ralliement-2/"
    assert attrs["max_height_m"] == 1.9
    assert attrs["structure_type"] == "ouvrage"
    assert attrs["free"] is False
    assert attrs["pmr_spaces"] == 9
    assert attrs["ev_chargers"] == 3
    assert attrs["rate_1h"] == 0.0
    assert attrs["rate_24h"] == 20.0
    expected = {
        "latitude",
        "longitude",
        "address",
        "url",
        "max_height_m",
        "structure_type",
        "free",
        "pmr_spaces",
        "ev_chargers",
        "rate_1h",
        "rate_2h",
        "rate_3h",
        "rate_4h",
        "rate_24h",
    }
    assert expected <= set(attrs)
    assert expected <= AvailableSpacesSensor._unrecorded_attributes


@pytest.mark.parametrize(
    "options",
    [
        {
            CONF_PARKINGS: ["Nouveau", "Ralliement"],
            CONF_SCAN_INTERVAL: 10,
            CONF_FULL_THRESHOLD: 95,
        }
    ],
)
async def test_unknown_capacity(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMocker,
    realtime: dict,
) -> None:
    realtime["results"].append({"nom": "Nouveau", "disponible": 42})
    set_realtime(mock_api, json=realtime)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert state(hass, "sensor", "nouveau_available_spaces").state == "42"
    assert state(hass, "sensor", "nouveau_occupancy").state == STATE_UNAVAILABLE
    assert entity_id(hass, "sensor", "nouveau_capacity") is None
    assert state(hass, "binary_sensor", "nouveau_full").state == STATE_UNAVAILABLE
    attrs = state(hass, "sensor", "nouveau_available_spaces").attributes
    assert attrs["latitude"] is None


async def test_missing_from_response(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_api: AiohttpClientMocker,
    realtime: dict,
) -> None:
    realtime["results"] = [r for r in realtime["results"] if r["nom"] != "Mail"]
    set_realtime(mock_api, json=realtime)
    await init_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert state(hass, "sensor", "mail_available_spaces").state == STATE_UNAVAILABLE
    assert state(hass, "sensor", "mail_occupancy").state == STATE_UNAVAILABLE
    assert state(hass, "binary_sensor", "mail_full").state == STATE_UNAVAILABLE
    # Capacity is static and stays known.
    assert state(hass, "sensor", "mail_capacity").state == "960"
    assert state(hass, "sensor", "ralliement_available_spaces").state == "12"


async def test_update_failure(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_api: AiohttpClientMocker,
) -> None:
    set_realtime(mock_api, status=503, text="down")
    await init_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()
    for unique_id in ("ralliement_available_spaces", "ralliement_capacity"):
        assert state(hass, "sensor", unique_id).state == STATE_UNAVAILABLE


async def test_french_names(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AiohttpClientMocker
) -> None:
    hass.config.language = "fr"
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.parking_du_ralliement_places_libres").state == "12"
    assert hass.states.get("sensor.parking_du_ralliement_taux_d_occupation")
    assert hass.states.get("sensor.parking_du_chateau_capacite").state == "300"
    assert hass.states.get("binary_sensor.parking_du_ralliement_complet").state == "on"
    assert hass.states.get("binary_sensor.open_data_angers_donnees_figees")


async def test_invalid_reference_url_keeps_entities(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMocker,
    reference: dict,
) -> None:
    for record in reference["results"]:
        if record["id"] == "49007-P-006":
            record["url"] = "parking-angers.fr/ralliement"
    set_reference(mock_api, json=reference)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert state(hass, "sensor", "ralliement_available_spaces").state == "12"
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, "Ralliement"), config_entry.entry_id
    )
    assert (
        device.configuration_url == "http://parking-angers.fr/parking-du-ralliement-2/"
    )
