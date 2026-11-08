"""Sensors for the Parking Angers integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_PARKINGS
from .coordinator import ParkingAngersConfigEntry
from .entity import ParkingEntity, get_static
from .models import RATE_KEYS

UNIT_SPACES = "places"

AVAILABLE_SPACES = SensorEntityDescription(
    key="available_spaces",
    translation_key="available_spaces",
    native_unit_of_measurement=UNIT_SPACES,
    state_class=SensorStateClass.MEASUREMENT,
)
OCCUPANCY = SensorEntityDescription(
    key="occupancy",
    translation_key="occupancy",
    native_unit_of_measurement=PERCENTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=0,
)
CAPACITY = SensorEntityDescription(
    key="capacity",
    translation_key="capacity",
    native_unit_of_measurement=UNIT_SPACES,
    entity_category=EntityCategory.DIAGNOSTIC,
)

STATIC_ATTRIBUTES = (
    "latitude",
    "longitude",
    "address",
    "url",
    "max_height_m",
    "structure_type",
    "free",
    "pmr_spaces",
    "ev_chargers",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParkingAngersConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for key in entry.options.get(CONF_PARKINGS, []):
        entities.append(AvailableSpacesSensor(coordinator, key, AVAILABLE_SPACES))
        entities.append(OccupancySensor(coordinator, key, OCCUPANCY))
        if get_static(coordinator, key).capacity is not None:
            entities.append(CapacitySensor(coordinator, key, CAPACITY))
    async_add_entities(entities)


class AvailableSpacesSensor(ParkingEntity, SensorEntity):
    """Number of free spaces."""

    _unrecorded_attributes = frozenset(
        {*STATIC_ATTRIBUTES, *(f"rate_{k}" for k in RATE_KEYS)}
    )

    @property
    def native_value(self) -> int | None:
        """Return the number of free spaces."""
        return parking.available if (parking := self.parking) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the static information about the car park."""
        if (parking := self.parking) is None:
            return None
        static = parking.static
        attrs: dict[str, Any] = {
            name: getattr(static, name) for name in STATIC_ATTRIBUTES
        }
        attrs.update({f"rate_{k}": static.rates.get(k) for k in RATE_KEYS})
        return attrs


class OccupancySensor(ParkingEntity, SensorEntity):
    """Occupancy rate."""

    @property
    def available(self) -> bool:
        """Unavailable when the capacity is unknown."""
        return super().available and self.parking.occupancy is not None  # type: ignore[union-attr]

    @property
    def native_value(self) -> float | None:
        """Return the occupancy rate."""
        return parking.occupancy if (parking := self.parking) else None


class CapacitySensor(ParkingEntity, SensorEntity):
    """Total number of spaces."""

    @property
    def available(self) -> bool:
        """Available as long as the coordinator works."""
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> int | None:
        """Return the capacity."""
        return get_static(self.coordinator, self._key).capacity
