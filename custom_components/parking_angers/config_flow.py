"""Config flow for the Parking Angers integration."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .api import ParkingAngersApi, ParkingAngersError
from .const import (
    CONF_FULL_THRESHOLD,
    CONF_PARKINGS,
    CONF_SCAN_INTERVAL,
    DEFAULT_FULL_THRESHOLD,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_FULL_THRESHOLD,
    MAX_SCAN_INTERVAL,
    MIN_FULL_THRESHOLD,
    MIN_SCAN_INTERVAL,
)
from .coordinator import ParkingAngersConfigEntry
from .models import ParkingStatic, load_statics

_LOGGER = logging.getLogger(__name__)

TITLE = "Parking Angers"


def _build_choices(
    keys: Iterable[str], statics: Mapping[str, ParkingStatic]
) -> list[SelectOptionDict]:
    """Return select options (value = real-time ``nom``) sorted by label."""
    options = [
        SelectOptionDict(value=key, label=statics[key].name if key in statics else key)
        for key in set(keys)
    ]
    return sorted(options, key=lambda option: option["label"].casefold())


def _build_schema(
    choices: list[SelectOptionDict], defaults: Mapping[str, Any]
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_PARKINGS, default=list(defaults[CONF_PARKINGS])
            ): SelectSelector(
                SelectSelectorConfig(
                    options=choices, multiple=True, mode=SelectSelectorMode.LIST
                )
            ),
            vol.Required(
                CONF_SCAN_INTERVAL, default=defaults[CONF_SCAN_INTERVAL]
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL,
                    max=MAX_SCAN_INTERVAL,
                    step=1,
                    unit_of_measurement="min",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_FULL_THRESHOLD, default=defaults[CONF_FULL_THRESHOLD]
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_FULL_THRESHOLD,
                    max=MAX_FULL_THRESHOLD,
                    step=1,
                    unit_of_measurement="%",
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
        }
    )


def _validate(user_input: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Normalise user input and return (options, errors)."""
    options = {
        CONF_PARKINGS: list(user_input.get(CONF_PARKINGS) or []),
        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
        CONF_FULL_THRESHOLD: int(user_input[CONF_FULL_THRESHOLD]),
    }
    errors = {} if options[CONF_PARKINGS] else {CONF_PARKINGS: "no_parking_selected"}
    return options, errors


class ParkingAngersConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._choices: list[SelectOptionDict] | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ParkingAngersConfigEntry,
    ) -> ParkingAngersOptionsFlow:
        """Return the options flow."""
        return ParkingAngersOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the car parks to follow."""
        errors: dict[str, str] = {}
        if user_input is not None and self._choices is not None:
            options, errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(title=TITLE, data={}, options=options)
            defaults: dict[str, Any] = options
        else:
            defaults = {}

        if self._choices is None:
            api = ParkingAngersApi(async_get_clientsession(self.hass))
            try:
                availability = await api.async_get_availability()
            except ParkingAngersError as err:
                _LOGGER.debug("Cannot reach data.angers.fr: %s", err)
                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema({}),
                    errors={"base": "cannot_connect"},
                )
            statics = await self.hass.async_add_executor_job(load_statics)
            self._choices = _build_choices(availability, statics)

        if not defaults:
            defaults = {
                CONF_PARKINGS: [choice["value"] for choice in self._choices],
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                CONF_FULL_THRESHOLD: DEFAULT_FULL_THRESHOLD,
            }
        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(self._choices, defaults),
            errors=errors,
        )


class ParkingAngersOptionsFlow(OptionsFlowWithReload):
    """Change the selected car parks and settings."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        entry: ParkingAngersConfigEntry = self.config_entry
        defaults: Mapping[str, Any] = {
            CONF_PARKINGS: entry.options.get(CONF_PARKINGS, []),
            CONF_SCAN_INTERVAL: entry.options.get(
                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
            ),
            CONF_FULL_THRESHOLD: entry.options.get(
                CONF_FULL_THRESHOLD, DEFAULT_FULL_THRESHOLD
            ),
        }
        if user_input is not None:
            options, errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(data=options)
            defaults = options

        if entry.state is ConfigEntryState.LOADED and entry.runtime_data.data:
            coordinator = entry.runtime_data
            statics = {
                key: state.static for key, state in coordinator.data.parkings.items()
            }
            statics = {**coordinator.statics, **statics}
            keys = set(coordinator.data.parkings)
        else:
            statics = await self.hass.async_add_executor_job(load_statics)
            keys = set(statics)
        keys |= set(entry.options.get(CONF_PARKINGS, []))

        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(_build_choices(keys, statics), defaults),
            errors=errors,
        )
