"""Base entities for the Parking Angers integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import ATTRIBUTION, DOMAIN, MANUFACTURER, SERVICE_DEVICE_ID
from .coordinator import ParkingAngersCoordinator
from .models import ParkingState, ParkingStatic


def get_static(coordinator: ParkingAngersCoordinator, key: str) -> ParkingStatic:
    """Return the best known static data for a car park."""
    if coordinator.data and (state := coordinator.data.parkings.get(key)):
        return state.static
    return coordinator.statics.get(key) or ParkingStatic.unknown(key)


class ParkingEntity(CoordinatorEntity[ParkingAngersCoordinator]):
    """An entity attached to a car park device."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: ParkingAngersCoordinator,
        key: str,
        description: EntityDescription,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._key = key
        self._attr_unique_id = f"{slugify(key)}_{description.key}"
        static = get_static(coordinator, key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, key)},
            name=static.name,
            manufacturer=MANUFACTURER,
            model=static.structure_type,
            configuration_url=static.url,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def parking(self) -> ParkingState | None:
        """Return the current state of the car park, if received."""
        return self.coordinator.data.parkings.get(self._key)

    @property
    def available(self) -> bool:
        """Unavailable when the car park is missing from the last response."""
        return super().available and self.parking is not None


class OpenDataEntity(CoordinatorEntity[ParkingAngersCoordinator]):
    """An entity attached to the open data service device."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self, coordinator: ParkingAngersCoordinator, description: EntityDescription
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = description.key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, SERVICE_DEVICE_ID)},
            name="Open data Angers",
            manufacturer=MANUFACTURER,
            model="data.angers.fr",
            configuration_url="https://data.angers.fr/explore/dataset/parking-angers/",
            entry_type=DeviceEntryType.SERVICE,
        )
