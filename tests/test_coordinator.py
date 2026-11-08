"""Tests for the coordinator."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.parking_angers.const import DOMAIN, ISSUE_STALE_DATA
from custom_components.parking_angers.coordinator import ParkingAngersCoordinator
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from .conftest import (
    REFERENCE_DATASET,
    load_fixture,
    set_realtime,
    set_reference,
)

pytestmark = pytest.mark.usefixtures("no_platforms")


def _coordinator(entry: MockConfigEntry) -> ParkingAngersCoordinator:
    return entry.runtime_data


def _reference_calls(aioclient_mock: AiohttpClientMocker) -> int:
    return sum(REFERENCE_DATASET in str(call[1]) for call in aioclient_mock.mock_calls)


async def test_setup_and_merge(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    assert init_integration.state is ConfigEntryState.LOADED
    coordinator = _coordinator(init_integration)
    data = coordinator.data
    assert len(data.parkings) == 19
    ralliement = data.parkings["Ralliement"]
    assert ralliement.available == 12
    assert ralliement.static.name == "Parking du Ralliement"
    assert ralliement.static.capacity == 432
    assert data.parkings["Chateau"].static.capacity == 300
    assert coordinator.reference_loaded_at is not None
    assert coordinator.unmapped == set()
    assert not data.stale

    await hass.config_entries.async_unload(init_integration.entry_id)
    assert init_integration.state is ConfigEntryState.NOT_LOADED


async def test_api_reference_has_priority(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMocker,
    reference: dict,
) -> None:
    for record in reference["results"]:
        if record["id"] == "49007-P-006":
            record["nb_places"] = 500
            record["nom"] = "Ralliement (nouveau)"
            record["url"] = None
    set_reference(mock_api, json=reference)
    await hass.config_entries.async_setup(config_entry.entry_id)
    static = _coordinator(config_entry).data.parkings["Ralliement"].static
    assert static.capacity == 500
    assert static.name == "Ralliement (nouveau)"
    assert static.url == "http://parking-angers.fr/parking-du-ralliement-2/"


async def test_reference_failure_falls_back(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
) -> None:
    set_reference(mock_api, status=500, text="boom")
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.LOADED
    coordinator = _coordinator(config_entry)
    assert coordinator.reference_loaded_at is None
    assert coordinator.data.parkings["Ralliement"].static.capacity == 432
    assert "Could not load the reference dataset" in caplog.text

    # Not retried at every update...
    freezer.tick(timedelta(minutes=10))
    await coordinator.async_refresh()
    assert _reference_calls(mock_api) == 1
    # ...but after one hour.
    set_reference(mock_api, json=load_fixture("reference.json"))
    freezer.tick(timedelta(hours=1))
    await coordinator.async_refresh()
    assert _reference_calls(mock_api) == 2
    assert coordinator.reference_loaded_at is not None


async def test_reference_reloaded_after_24h(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_api: AiohttpClientMocker,
) -> None:
    coordinator = _coordinator(init_integration)
    assert _reference_calls(mock_api) == 1
    freezer.tick(timedelta(hours=23))
    await coordinator.async_refresh()
    assert _reference_calls(mock_api) == 1
    freezer.tick(timedelta(hours=1))
    await coordinator.async_refresh()
    assert _reference_calls(mock_api) == 2
    assert coordinator.reference_loaded_at == dt_util.utcnow()


async def test_unknown_parking(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMocker,
    realtime: dict,
    caplog: pytest.LogCaptureFixture,
) -> None:
    realtime["results"].append({"nom": "Nouveau", "disponible": 42})
    set_realtime(mock_api, json=realtime)
    await hass.config_entries.async_setup(config_entry.entry_id)
    coordinator = _coordinator(config_entry)
    state = coordinator.data.parkings["Nouveau"]
    assert state.available == 42
    assert state.static.name == "Nouveau"
    assert state.occupancy is None
    assert coordinator.unmapped == {"Nouveau"}
    await coordinator.async_refresh()
    assert caplog.text.count("Unknown car park 'Nouveau'") == 1


async def test_over_capacity_logged_once(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMocker,
    realtime: dict,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG", logger="custom_components.parking_angers")
    for record in realtime["results"]:
        if record["nom"] == "Confluences":
            record["disponible"] = 45
    set_realtime(mock_api, json=realtime)
    await hass.config_entries.async_setup(config_entry.entry_id)
    coordinator = _coordinator(config_entry)
    assert coordinator.data.parkings["Confluences"].occupancy == 0
    await coordinator.async_refresh()
    assert caplog.text.count("Confluences: 45 free spaces") == 1


@pytest.mark.parametrize(
    "kwargs",
    [{"status": 503, "text": "down"}, {"status": 404, "json": {"error_code": "x"}}],
)
async def test_first_refresh_failure(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMocker,
    kwargs: dict,
) -> None:
    set_realtime(mock_api, **kwargs)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_update_failure_and_rate_limit(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_api: AiohttpClientMocker,
) -> None:
    coordinator = _coordinator(init_integration)
    set_realtime(mock_api, status=503, text="down")
    await coordinator.async_refresh()
    assert not coordinator.last_update_success

    freezer.move_to("2026-11-08 22:00:00+00:00")
    set_realtime(
        mock_api,
        status=429,
        json={"error_code": "TooManyRequests"},
        headers={"X-RateLimit-Reset": "2026-11-09T00:00:00+00:00"},
    )
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    # The next refresh is postponed to the quota reset.
    assert coordinator._retry_after == 2 * 3600

    set_realtime(mock_api, status=429, json={"error_code": "TooManyRequests"})
    with pytest.raises(UpdateFailed) as err:
        await coordinator._async_update_data()
    assert err.value.retry_after is None

    set_realtime(mock_api, json=load_fixture("realtime.json"))
    await coordinator.async_refresh()
    assert coordinator.last_update_success


async def test_stale_detection(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_api: AiohttpClientMocker,
) -> None:
    coordinator = _coordinator(init_integration)
    issues = ir.async_get(hass)
    start = dt_util.utcnow()
    assert coordinator.data.last_change == start

    # Unchanged values for less than 3 h: nothing reported.
    freezer.tick(timedelta(hours=2, minutes=59))
    await coordinator.async_refresh()
    assert not coordinator.data.stale
    assert issues.async_get_issue(DOMAIN, ISSUE_STALE_DATA) is None

    # 3 h: stale, a repair issue is created, data stays available.
    freezer.tick(timedelta(minutes=1))
    await coordinator.async_refresh()
    assert coordinator.data.stale
    assert coordinator.last_update_success
    assert coordinator.data.last_change == start
    issue = issues.async_get_issue(DOMAIN, ISSUE_STALE_DATA)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert not issue.is_fixable

    # A value changes: back to normal, issue removed.
    set_realtime(mock_api, json=load_fixture("realtime_changed.json"))
    freezer.tick(timedelta(minutes=10))
    await coordinator.async_refresh()
    assert not coordinator.data.stale
    assert coordinator.data.last_change == dt_util.utcnow()
    assert issues.async_get_issue(DOMAIN, ISSUE_STALE_DATA) is None


async def test_issue_removed_on_unload(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
) -> None:
    coordinator = _coordinator(init_integration)
    freezer.tick(timedelta(hours=3))
    await coordinator.async_refresh()
    issues = ir.async_get(hass)
    assert issues.async_get_issue(DOMAIN, ISSUE_STALE_DATA) is not None
    await hass.config_entries.async_unload(init_integration.entry_id)
    assert issues.async_get_issue(DOMAIN, ISSUE_STALE_DATA) is None
