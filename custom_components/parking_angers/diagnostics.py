"""Diagnostics for the Parking Angers integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import ParkingAngersConfigEntry


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ParkingAngersConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry (nothing sensitive to redact)."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "last_fetch": _iso(coordinator.last_fetch),
        "stale": data.stale if data else None,
        "last_change": _iso(coordinator.last_change),
        "reference_loaded_at": _iso(coordinator.reference_loaded_at),
        "parking_count": len(data.parkings) if data else 0,
        "unmapped": sorted(coordinator.unmapped),
        "last_realtime_response": coordinator.api.last_availability_raw,
    }
