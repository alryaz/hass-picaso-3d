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

from custom_components.picaso_3d.api import DEFAULT_INTERACTION_PORT, Picaso3DPrinter
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

    __slots__ = ("_update_methods",)

    def __init__(self, *args, **kwargs) -> None:
        self._update_methods = {}
        super().__init__(*args, **kwargs)
        self.logger.debug(
            "Created coordinator %s with scan interval %s", self, self.update_interval
        )

    def subscribe_entity(self, entity: Picaso3DCoordinatorEntity):
        entities = self._update_methods.setdefault(
            entity.entity_description.update_method_name, []
        )
        if entity not in entities:
            entities.append(entity)
            self.logger.debug(
                "Subscribed entity %s to coordinator %s with method %s",
                entity,
                self,
                entity.entity_description.update_method_name,
            )

    def unsubscribe_entity(self, entity: Picaso3DCoordinatorEntity):
        update_method_name = entity.entity_description.update_method_name
        entities = self._update_methods.get(update_method_name, [])
        while entity in entities:
            entities.remove(entity)
            self.logger.debug(
                "Unsubscribed entity %s from coordinator %s with method %s",
                entity,
                self,
                update_method_name,
            )
        if not entities:
            del self._update_methods[update_method_name]
            self.logger.debug(
                "Clearing up empty queue for method %s on coordinator %s",
                update_method_name,
                self,
            )

    @property
    def printer(self) -> Picaso3DPrinter:
        return self.hass.data[DOMAIN][self.config_entry.entry_id][0]

    async def _async_update_data(self) -> dict[str, Any]:
        self.logger.debug("Updating data for %s", self)
        data = {}
        if self._update_methods:
            exceptions = []
            one_success = False
            for method_name, entities in self._update_methods.items():
                method = getattr(self.printer, method_name)
                try:
                    one_success = True
                    result = await method()
                except Exception as exc:
                    result = exc
                    exceptions.append(exc)
                data[method_name] = result
            if not one_success:
                if len(exceptions) == 1:
                    raise exceptions[0]
                raise HomeAssistantError(
                    f"All update methods ({', '.join(self._update_methods)} failed"
                )
        self.logger.debug("Finished data update for %s", self)
        return data


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

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        await super().async_added_to_hass()
        if self.entity_description.update_method_name is None:
            return
        self.coordinator.subscribe_entity(self)
        self.async_on_remove(lambda: self.coordinator.unsubscribe_entity(self))

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from updates."""
        self.coordinator.unsubscribe_entity(self)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            manufacturer=DEFAULT_MANUFACTURER,
            serial_number=self.printer.serial,
            sw_version=self.printer.firmware_version,
            hw_version=self.printer.hardware_version,
            model_id=self.printer.hw_version_major,
            model=self.printer.type.name,
            name=self.printer.name,
            identifiers={(DOMAIN, self.printer.serial)},
            connections={(CONNECTION_NETWORK_MAC, self.printer.mac)}
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
        collected_data = self.coordinator.data
        try:
            result = collected_data[self.entity_description.update_method_name]
        except KeyError:
            self.logger.debug(
                "No data for %s in %s",
                self.entity_description.update_method_name,
                collected_data,
            )
            self._attr_available = False
        else:
            if isinstance(result, Exception):
                self.logger.error("Error during update: %s", result)
                self._attr_available = False
            else:
                self._attr_available = result is not None
                if self._attr_available:
                    self._process_coordinator_data(result)

        super()._handle_coordinator_update()


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

    # Create sequential coordinator
    coordinator = Picaso3DUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name="PICASO 3D Sequential Updater",
        update_interval=timedelta(seconds=entry.data[CONF_SCAN_INTERVAL]),
    )

    # Store data for future use
    hass.data[DOMAIN][entry.entry_id] = (printer, coordinator)

    # up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Since updates are sequential, perform like this
    try:
        await coordinator.async_config_entry_first_refresh()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger_kwargs = {}
        if _LOGGER.isEnabledFor(logging.DEBUG):
            logger_kwargs["exc_info"] = exc
        _LOGGER.error(
            "Error during first refresh of '%s': %s",
            coordinator,
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
        coordinator= hass.data[DOMAIN][entry.entry_id][1]
        entities = [
            platform_class(
                coordinator=,
                entity_description=entity_description,
                logger=logger,
            )
            for entity_description in entity_descriptions
            if entity_description.check_supported is None
            or entity_description.check_supported(coordinator.printer)
        ]

        logger.debug("Entities added : %i", len(entities))

        async_add_entities(entities)

        return True

    return async_setup_entry
