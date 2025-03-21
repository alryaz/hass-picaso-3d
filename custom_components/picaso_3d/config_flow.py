"""Adds config flow for Picaso3D Integration."""

from __future__ import annotations

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SelectOptionDict,
)

from custom_components.picaso_3d import async_initialize_printer_connection
from custom_components.picaso_3d.api import DEFAULT_INTERACTION_PORT, Picaso3DPrinter
from custom_components.picaso_3d.const import DOMAIN, DEFAULT_SCAN_INTERVAL, CONF_PORT

_LOGGER = logging.getLogger(__name__)

CONFIG_FLOW_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT, default=DEFAULT_INTERACTION_PORT): cv.port,
        vol.Optional(
            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
        ): cv.positive_int,
    }
)

CONF_SERIAL = "serial"


class Picaso3DFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Picaso3D."""

    VERSION = 2
    MINOR_VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self) -> None:
        self.discovered_printers = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        if self.discovered_printers is None:
            self.discovered_printers = await Picaso3DPrinter.search_printers()

        existing_serials = self._async_current_ids(include_ignore=True)
        valid_discovered_printers = []
        has_at_least_one_discovered_printer_configured = False
        for printer in self.discovered_printers:
            if not printer.serial:
                continue
            if printer.serial in existing_serials:
                has_at_least_one_discovered_printer_configured = True
                continue
            valid_discovered_printers.append(printer)

        if not valid_discovered_printers:
            # No printers found
            # noinspection PyTypeChecker
            return await self.async_step_setup(
                from_existing=has_at_least_one_discovered_printer_configured
            )

        if user_input is not None:
            for printer in valid_discovered_printers:
                if printer.serial == user_input[CONF_SERIAL]:
                    user_input[CONF_HOST] = printer.host
                    user_input[CONF_PORT] = DEFAULT_INTERACTION_PORT
                    user_input.pop(CONF_SERIAL)
                    # user_input[CONF_PORT] = printer.port
                    return await self.async_step_setup(user_input)

        select_options = [
            SelectOptionDict(
                value=printer.serial,
                label=f"{printer.name or printer.serial} ({printer.host})",
            )
            for printer in valid_discovered_printers
        ]

        data_schema = vol.Schema(
            {
                vol.Required(CONF_SERIAL): SelectSelector(
                    SelectSelectorConfig(
                        custom_value=True,
                        options=select_options,
                        mode=SelectSelectorMode.LIST,
                        multiple=False,
                    )
                ),
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): cv.positive_int,
            }
        )

        # noinspection PyTypeChecker
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(data_schema, user_input),
        )

    async def async_step_setup(
        self, user_input: dict[str, Any] | None = None, from_existing: bool = False
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors = {}
        schema = CONFIG_FLOW_SCHEMA

        if from_existing:
            errors["base"] = "discovered_printers_added"

        if user_input is not None:
            try:
                printer = await async_initialize_printer_connection(user_input)
            except OSError as exc:
                _LOGGER.error("Error communicating with given printer: %s", exc)
                errors[CONF_HOST] = "connection_error"
            else:
                if not printer.serial:
                    # noinspection PyTypeChecker
                    return self.async_abort(reason="empty_serial")

                await self.async_set_unique_id(printer.serial)
                self._abort_if_unique_id_configured()

                # noinspection PyTypeChecker
                return self.async_create_entry(
                    title=printer.name or printer.serial, data=user_input
                )

            schema = self.add_suggested_values_to_schema(schema, user_input)

        # noinspection PyTypeChecker
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
