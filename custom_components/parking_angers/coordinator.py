"""Data update coordinator for the Parking Angers integration."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ParkingAngersApi, ParkingAngersError, ParkingAngersRateLimitError
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ISSUE_STALE_DATA,
    MAX_RETRY_AFTER,
    REFERENCE_REFRESH,
    STALE_AFTER,
)
from .models import ParkingData, ParkingState, ParkingStatic

_LOGGER = logging.getLogger(__name__)

# Delay before retrying a failed reference download.
REFERENCE_RETRY = timedelta(hours=1)

type ParkingAngersConfigEntry = ConfigEntry[ParkingAngersCoordinator]


class ParkingAngersCoordinator(DataUpdateCoordinator[ParkingData]):
    """Fetch real-time availability and merge it with reference data."""

    config_entry: ParkingAngersConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ParkingAngersConfigEntry,
        api: ParkingAngersApi,
        statics: dict[str, ParkingStatic],
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.api = api
        self.statics = statics
        self.reference: dict[str, dict[str, Any]] = {}
        self.reference_loaded_at: datetime | None = None
        self._reference_next_attempt: datetime | None = None
        self.last_fetch: datetime | None = None
        self.last_change: datetime | None = None
        self.unmapped: set[str] = set()
        self._last_values: dict[str, int] | None = None
        self._stale = False
        self._over_capacity_logged: set[str] = set()

    async def _async_update_data(self) -> ParkingData:
        now = dt_util.utcnow()
        try:
            values = await self.api.async_get_availability()
        except ParkingAngersRateLimitError as err:
            retry_after = self._retry_delay(err.retry_after, now)
            raise UpdateFailed(
                f"API quota exceeded, retrying in {retry_after:.0f} s",
                retry_after=retry_after,
            ) from err
        except ParkingAngersError as err:
            raise UpdateFailed(str(err)) from err

        self.last_fetch = now
        await self._async_refresh_reference(now)
        self._update_stale(values, now)

        parkings: dict[str, ParkingState] = {}
        for key, available in values.items():
            static = self.statics.get(key)
            if static is None:
                if key not in self.unmapped:
                    _LOGGER.info(
                        "Unknown car park %r received from data.angers.fr: only "
                        "the number of free spaces is available",
                        key,
                    )
                    self.unmapped.add(key)
                static = ParkingStatic.unknown(key)
            elif static.ref_id:
                static = static.merged_with(self.reference.get(static.ref_id))
            if (
                static.capacity is not None
                and available > static.capacity
                and key not in self._over_capacity_logged
            ):
                self._over_capacity_logged.add(key)
                _LOGGER.debug(
                    "%s: %s free spaces for a capacity of %s, occupancy set to 0",
                    key,
                    available,
                    static.capacity,
                )
            parkings[key] = ParkingState(static=static, available=available)

        return ParkingData(
            parkings=parkings, stale=self._stale, last_change=self.last_change
        )

    def _retry_delay(self, reset: datetime | None, now: datetime) -> float:
        """Seconds to wait after a 429, never shorter than the normal interval.

        A reset instant already past (clock skew, stale header) would otherwise
        make the coordinator retry immediately, in a loop; one far in the future
        would freeze the integration.
        """
        interval = self.update_interval or timedelta(0)
        delay = (reset - now) if reset else interval
        return min(max(delay, interval), MAX_RETRY_AFTER).total_seconds()

    async def _async_refresh_reference(self, now: datetime) -> None:
        """Reload the reference dataset when needed; never raises."""
        if self._reference_next_attempt and now < self._reference_next_attempt:
            return
        try:
            reference = await self.api.async_get_reference()
        except ParkingAngersError as err:
            self._reference_next_attempt = now + REFERENCE_RETRY
            _LOGGER.warning(
                "Could not load the reference dataset, using embedded data: %s", err
            )
            return
        self.reference = reference
        self.reference_loaded_at = now
        self._reference_next_attempt = now + REFERENCE_REFRESH

    def _update_stale(self, values: dict[str, int], now: datetime) -> None:
        """Detect a real-time feed that no longer changes."""
        if self._last_values is None or values != self._last_values:
            self.last_change = now
        self._last_values = values
        stale = now - (self.last_change or now) >= STALE_AFTER
        if stale and not self._stale:
            _LOGGER.warning(
                "data.angers.fr values have not changed since %s", self.last_change
            )
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                ISSUE_STALE_DATA,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_STALE_DATA,
                translation_placeholders={
                    "last_change": dt_util.as_local(self.last_change).strftime(
                        "%Y-%m-%d %H:%M"
                    )
                },
            )
        elif not stale and self._stale:
            _LOGGER.info("data.angers.fr values are changing again")
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_STALE_DATA)
        self._stale = stale
