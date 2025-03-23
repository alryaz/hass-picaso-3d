"""Custom integration for Picaso3D printers with Home Assistant."""

from __future__ import annotations

__all__ = (
    # Home Assistant requirements
    "async_setup_entry",
    "async_setup",
    "async_unload_entry",
    # Component methods
    "async_initialize_printer_connection",
    "make_platform_async_setup_entry",
    # Component classes
    "Picaso3DCoordinatorEntity",
    "Picaso3DUpdateCoordinator",
    "Picaso3DCoordinatorEntityDescription",
    # Extra
    "TMethodName",
    "support_check_multi_nozzle",
    # Submodules
    "api",
    "binary_sensor",
    "button",
    "config_flow",
    "const",
    "sensor",
)

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import (
    Callable,
    final,
    Any,
    Mapping,
    Iterable,
    Awaitable,
    TypeVar,
    Generic,
)

import aiohttp
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo, CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)

from custom_components.picaso_3d.api import (
    DEFAULT_INTERACTION_PORT,
    Picaso3DPrinter,
    PrinterType,
)
from custom_components.picaso_3d.const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    CONF_PORT,
    DEFAULT_MANUFACTURER,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)

PICASO3D_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_INTERACTION_PORT): cv.port,
        vol.Optional(
            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
        ): cv.positive_int,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({cv.slug: PICASO3D_SCHEMA})}, extra=vol.ALLOW_EXTRA
)

TMethodName = Callable[[Picaso3DPrinter], Any] | str


@dataclass(frozen=True, kw_only=True)
class Picaso3DCoordinatorEntityDescription(EntityDescription):
    """Describes Picaso3D entity."""

    update_method_name: TMethodName
    """Method to request data."""

    attribute: str = None
    """Attribute to extract from the data."""

    converter: Callable[[Any], Any] | None = None
    """Function to convert the extracted attribute."""

    check_supported: Callable[[Picaso3DPrinter], bool] | None = None
    """Check whether entity is supported by given printer."""

    icon: str | Callable[[Picaso3DCoordinatorEntity], str | None] | None = None

    def __post_init__(self):
        if not (
            isinstance(self.update_method_name, str) or self.update_method_name is None
        ):
            object.__setattr__(
                self, "update_method_name", self.update_method_name.__name__
            )


class Picaso3DUpdateCoordinator(DataUpdateCoordinator):
    """Picaso3D Update Coordinator class."""

    __slots__ = ()

    def __init__(self, *args, update_method_name: str, **kwargs) -> None:
        assert "update_method" not in kwargs
        super().__init__(
            *args,
            update_method=lambda: getattr(self.printer, update_method_name)(),
            **kwargs,
        )
        self.logger.debug(
            "Created coordinator %s with scan interval %s",
            self.name,
            self.update_interval,
        )

    @property
    def printer(self) -> Picaso3DPrinter:
        return self.hass.data[DOMAIN][self.config_entry.entry_id][0]


_TPicaso3DCoordinatorEntityDescription = TypeVar(
    "_TPicaso3DCoordinatorEntityDescription", bound=Picaso3DCoordinatorEntityDescription
)


class Picaso3DCoordinatorEntity(
    CoordinatorEntity[Picaso3DUpdateCoordinator],
    Generic[_TPicaso3DCoordinatorEntityDescription],
):
    """Picaso3D Coordinator Entity class."""

    entity_description: _TPicaso3DCoordinatorEntityDescription

    _attr_has_entity_name = True

    def __init__(
        self,
        entity_description: _TPicaso3DCoordinatorEntityDescription,
        coordinator: Picaso3DUpdateCoordinator,
        logger: logging.Logger | logging.LoggerAdapter = _LOGGER,
    ) -> None:
        """Initialize the sensor."""
        CoordinatorEntity.__init__(self, coordinator)

        self.entity_description = entity_description
        self.logger = logger
        self._attr_unique_id = (
            f"{self.coordinator.config_entry.unique_id}__{entity_description.key}"
        )
        self._attr_native_value = None
        self._attr_available = False

    @property
    def icon(self) -> str | None:
        """Return the icon."""
        icon = self.entity_description.icon
        if icon is None:
            return None
        if callable(icon):
            return icon(self)
        return icon

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            manufacturer=DEFAULT_MANUFACTURER,
            serial_number=self.printer.serial,
            sw_version=self.printer.firmware_version,
            hw_version=self.printer.hardware_version,
            model_id=self.printer.hw_version_major,
            model=self.printer.type.friendly_name,
            name=self.printer.name,
            identifiers={(DOMAIN, self.printer.serial)},
            connections={(CONNECTION_NETWORK_MAC, self.printer.mac)},
        )

    @property
    def printer(self) -> Picaso3DPrinter:
        return self.coordinator.printer

    async def async_call_method_by_name(self, method_name: str, *args, **kwargs):
        return await getattr(self.printer, method_name)(*args, **kwargs)

    @callback
    def _process_coordinator_data(self, value) -> None:
        attribute = self.entity_description.attribute
        if attribute is not None:
            value = getattr(value, attribute)
        if value is None:
            self.logger.debug("%s=unavailable", self)
            self._attr_available = False
        elif self.entity_description.converter:
            value = self.entity_description.converter(value)
        self._attr_native_value = value

    @final
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data = self.coordinator.data
        self._attr_available = data is not None

        if self._attr_available:
            self._process_coordinator_data(data)

        super()._handle_coordinator_update()


def support_check_multi_nozzle(printer: Picaso3DPrinter) -> bool:
    if not isinstance(printer.type, PrinterType) or printer.type == PrinterType.UNKNOWN:
        return False
    return printer.type.is_multi_nozzle


async def async_initialize_printer_connection(
    data: Mapping[str, Any],
    options: Mapping[str, Any] | None = None,
) -> Picaso3DPrinter:
    """Initialize Picaso3D API from configuration."""
    printer = Picaso3DPrinter(
        host=data[CONF_HOST],
        port=data.get(CONF_PORT, DEFAULT_INTERACTION_PORT),
    )
    await printer.update_printer_info()
    return printer


# noinspection PyUnusedLocal
async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Picaso3D component."""
    hass.data[DOMAIN] = {}
    return True


@callback
def async_get_coordinator(
    hass: HomeAssistant, entry: ConfigEntry, update_method_name: str
) -> Picaso3DUpdateCoordinator:
    # Iterate over the collected update_method_names
    coordinators = hass.data[DOMAIN][entry.entry_id][1]
    if update_method_name not in coordinators:
        coordinator = Picaso3DUpdateCoordinator(
            hass,
            _LOGGER,
            config_entry=entry,
            name="PICASO 3D Updater for '{}' method".format(update_method_name),
            update_interval=timedelta(seconds=entry.data[CONF_SCAN_INTERVAL]),
            update_method_name=update_method_name,
        )
        coordinators[update_method_name] = coordinator
    return coordinators[update_method_name]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""

    # Initialize and connect API
    try:
        printer = await async_initialize_printer_connection(entry.data, entry.options)
    except (aiohttp.ClientConnectorError, aiohttp.ClientResponseError) as exc:
        logger_kwargs = {}
        if _LOGGER.isEnabledFor(logging.DEBUG):
            logger_kwargs["exc_info"] = exc
        _LOGGER.warning("Error during initial communication: %s", exc, **logger_kwargs)
        raise ConfigEntryNotReady("Error connecting to the Picaso3D printer") from exc

    coordinators: dict[str, Picaso3DUpdateCoordinator] = {}

    # Store data for future use
    hass.data[DOMAIN][entry.entry_id] = (printer, coordinators)

    # up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Since updates are sequential, perform like this
    coordinator_refresh_tasks = {
        coordinator: hass.async_create_task(
            coordinator.async_config_entry_first_refresh()
        )
        for coordinator in coordinators.values()
    }
    if coordinator_refresh_tasks:
        await asyncio.wait(
            coordinator_refresh_tasks.values(), return_when=asyncio.ALL_COMPLETED
        )
        for coordinator, task in coordinator_refresh_tasks.items():
            exc = task.exception()
            if exc and not isinstance(exc, asyncio.CancelledError):
                logger_kwargs = {}
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    logger_kwargs["exc_info"] = exc
                _LOGGER.error(
                    "Error during first refresh of '%s': %s",
                    coordinator.name,
                    exc,
                    **logger_kwargs,
                )

    _LOGGER.debug("Finished setting up config entry %s", entry.entry_id)

    return True


async def async_unload_entry(hass: HomeAssistant, entry):
    """Unload Picaso3D entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if not unload_ok:
        return False

    hass.data[DOMAIN].pop(entry.entry_id)
    return True


DEFAULT_UPDATE_METHOD_NAME = "get_printer_state"


def make_platform_async_setup_entry(
    entity_descriptions: Iterable[Picaso3DCoordinatorEntityDescription],
    platform_class: type[Picaso3DCoordinatorEntity],
    logger: logging.Logger | logging.LoggerAdapter = _LOGGER,
) -> Callable[[HomeAssistant, ConfigEntry, AddEntitiesCallback], Awaitable[bool]]:
    # noinspection PyShadowingNames
    async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
    ) -> bool:
        """Do the setup entry."""
        printer = hass.data[DOMAIN][entry.entry_id][0]
        entities = [
            platform_class(
                coordinator=async_get_coordinator(
                    hass,
                    entry,
                    entity_description.update_method_name or DEFAULT_UPDATE_METHOD_NAME,
                ),
                entity_description=entity_description,
                logger=logger,
            )
            for entity_description in entity_descriptions
            if entity_description.check_supported is None
            or entity_description.check_supported(printer)
        ]

        logger.debug("Entities added : %i", len(entities))

        async_add_entities(entities)

        return True

    return async_setup_entry
