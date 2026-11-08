"""The Parking Angers integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ParkingAngersApi
from .const import CONF_PARKINGS, DOMAIN, ISSUE_STALE_DATA, SERVICE_DEVICE_ID
from .coordinator import ParkingAngersConfigEntry, ParkingAngersCoordinator
from .models import load_statics

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant, entry: ParkingAngersConfigEntry
) -> bool:
    """Set up Parking Angers from a config entry."""
    statics = await hass.async_add_executor_job(load_statics)
    api = ParkingAngersApi(async_get_clientsession(hass))
    coordinator = ParkingAngersCoordinator(hass, entry, api, statics)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _remove_unselected_devices(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ParkingAngersConfigEntry
) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_STALE_DATA)
    return unloaded


def _remove_unselected_devices(
    hass: HomeAssistant, entry: ParkingAngersConfigEntry
) -> None:
    """Detach the devices of car parks that are no longer selected."""
    keep = set(entry.options.get(CONF_PARKINGS, [])) | {SERVICE_DEVICE_ID}
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        keys = {ident[1] for ident in device.identifiers if ident[0] == DOMAIN}
        if keys and not keys & keep:
            registry.async_update_device(
                device.id, remove_config_entry_id=entry.entry_id
            )
