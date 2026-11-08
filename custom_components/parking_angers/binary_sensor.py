"""Binary sensors for the Parking Angers integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_FULL_THRESHOLD, CONF_PARKINGS, DEFAULT_FULL_THRESHOLD
from .coordinator import ParkingAngersConfigEntry
from .entity import OpenDataEntity, ParkingEntity

FULL = BinarySensorEntityDescription(key="full", translation_key="full")
STALE_DATA = BinarySensorEntityDescription(
    key="stale_data",
    translation_key="stale_data",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParkingAngersConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        FullBinarySensor(coordinator, key, FULL)
        for key in entry.options.get(CONF_PARKINGS, [])
    ]
    entities.append(StaleDataBinarySensor(coordinator, STALE_DATA))
    async_add_entities(entities)


class FullBinarySensor(ParkingEntity, BinarySensorEntity):
    """On when the occupancy reaches the configured threshold."""

    @property
    def available(self) -> bool:
        """Unavailable when the capacity is unknown."""
        return super().available and self.parking.occupancy is not None  # type: ignore[union-attr]

    @property
    def is_on(self) -> bool | None:
        """Return True if the car park is considered full."""
        if (parking := self.parking) is None or parking.occupancy is None:
            return None
        threshold = self.coordinator.config_entry.options.get(
            CONF_FULL_THRESHOLD, DEFAULT_FULL_THRESHOLD
        )
        return parking.occupancy >= threshold


class StaleDataBinarySensor(OpenDataEntity, BinarySensorEntity):
    """On when the real-time feed has not changed for a while."""

    @property
    def is_on(self) -> bool:
        """Return True if the data looks frozen."""
        return self.coordinator.data.stale

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the last time a value changed."""
        last_change = self.coordinator.data.last_change
        return {"last_change": last_change.isoformat() if last_change else None}
