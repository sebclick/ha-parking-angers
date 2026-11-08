"""Tests for the config and options flows."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.parking_angers.const import (
    CONF_FULL_THRESHOLD,
    CONF_PARKINGS,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import set_realtime


def _device(
    registry: dr.DeviceRegistry, entry: MockConfigEntry, key: str
) -> dr.DeviceEntry | None:
    return registry.async_get_device_by_identifier((DOMAIN, key), entry.entry_id)


def _choices(result) -> list[dict]:
    schema = result["data_schema"].schema
    key = next(k for k in schema if k == CONF_PARKINGS)
    return schema[key].config["options"]


def _default(result, name: str):
    schema = result["data_schema"].schema
    return next(k for k in schema if k == name).default()


async def test_user_flow(hass: HomeAssistant, mock_api: AiohttpClientMocker) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    choices = _choices(result)
    assert len(choices) == 19
    labels = [c["label"] for c in choices]
    assert labels == sorted(labels, key=str.casefold)
    assert {"value": "Chateau", "label": "Parking du Château"} in choices
    assert len(_default(result, CONF_PARKINGS)) == 19
    assert _default(result, CONF_SCAN_INTERVAL) == 10
    assert _default(result, CONF_FULL_THRESHOLD) == 95

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PARKINGS: ["Ralliement", "Mail"],
            CONF_SCAN_INTERVAL: 5.0,
            CONF_FULL_THRESHOLD: 90.0,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Parking Angers"
    assert result["data"] == {}
    assert result["options"] == {
        CONF_PARKINGS: ["Ralliement", "Mail"],
        CONF_SCAN_INTERVAL: 5,
        CONF_FULL_THRESHOLD: 90,
    }
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.LOADED


async def test_cannot_connect_then_retry(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, realtime: dict
) -> None:
    set_realtime(mock_api, status=503, text="down")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    set_realtime(mock_api, json=realtime)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}
    assert len(_choices(result)) == 19


async def test_no_parking_selected(
    hass: HomeAssistant, mock_api: AiohttpClientMocker
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PARKINGS: [], CONF_SCAN_INTERVAL: 10, CONF_FULL_THRESHOLD: 95},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PARKINGS: "no_parking_selected"}
    assert _default(result, CONF_PARKINGS) == []


async def test_single_instance(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_change_interval(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    coordinator = init_integration.runtime_data
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert len(_choices(result)) == 19
    assert set(_default(result, CONF_PARKINGS)) == set(
        init_integration.options[CONF_PARKINGS]
    )

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_PARKINGS: init_integration.options[CONF_PARKINGS],
            CONF_SCAN_INTERVAL: 2,
            CONF_FULL_THRESHOLD: 95,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options[CONF_SCAN_INTERVAL] == 2
    # Reloaded with a new coordinator.
    new_coordinator = init_integration.runtime_data
    assert new_coordinator is not coordinator
    assert new_coordinator.update_interval.total_seconds() == 120


async def test_options_unselected_device_removed(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    registry = dr.async_get(hass)
    entities = er.async_get(hass)
    assert _device(registry, init_integration, "Mail") is not None
    assert entities.async_get_entity_id("sensor", DOMAIN, "mail_available_spaces")

    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_PARKINGS: ["Ralliement"], CONF_SCAN_INTERVAL: 10, CONF_FULL_THRESHOLD: 95},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _device(registry, init_integration, "Mail") is None
    assert _device(registry, init_integration, "Ralliement") is not None
    assert _device(registry, init_integration, "open_data") is not None
    assert (
        entities.async_get_entity_id("sensor", DOMAIN, "mail_available_spaces") is None
    )


async def test_options_errors_and_missing_parking(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_api: AiohttpClientMocker,
    realtime: dict,
) -> None:
    # A selected car park disappears from the feed: it stays in the list.
    realtime["results"] = [r for r in realtime["results"] if r["nom"] != "Mail"]
    set_realtime(mock_api, json=realtime)
    await init_integration.runtime_data.async_refresh()
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    values = {c["value"] for c in _choices(result)}
    assert "Mail" in values
    assert len(values) == 19

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_PARKINGS: [], CONF_SCAN_INTERVAL: 10, CONF_FULL_THRESHOLD: 95},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PARKINGS: "no_parking_selected"}


async def test_options_entry_not_loaded(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert len(_choices(result)) == 19
