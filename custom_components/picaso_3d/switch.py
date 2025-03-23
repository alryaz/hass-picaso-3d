import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription

from custom_components.picaso_3d import (
    Picaso3DCoordinatorEntity,
    Picaso3DCoordinatorEntityDescription,
    make_platform_async_setup_entry,
    TMethodName,
)

from custom_components.picaso_3d.api import Picaso3DPrinter


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class Picaso3DSwitchEntityDescription(
    Picaso3DCoordinatorEntityDescription, SwitchEntityDescription
):
    """A class that represents Picaso3D entity description for switch object(s)."""

    turn_on_method_name: TMethodName
    turn_off_method_name: TMethodName
    update_method_name: TMethodName | None = None

    def __post_init__(self):
        super().__post_init__()
        for attribute in ("turn_on_method_name", "turn_off_method_name"):
            value = getattr(self, attribute)
            if not (isinstance(value, str) or value is None):
                object.__setattr__(self, attribute, value.__name__)


ENTITY_DESCRIPTIONS = (
    Picaso3DSwitchEntityDescription(
        key="locate",
        name="Locate",
        turn_on_method_name=Picaso3DPrinter.start_locating,
        turn_off_method_name=Picaso3DPrinter.stop_locating,
        icon="mdi:map-marker",
    ),
)


class Picaso3DSwitch(Picaso3DCoordinatorEntity, SwitchEntity):
    async def async_turn_on(self, **kwargs: Any) -> None:
        await getattr(self.printer, self.entity_description.turn_on_method_name)()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await getattr(self.printer, self.entity_description.turn_off_method_name)()

    def _process_coordinator_data(self, value) -> None:
        super()._process_coordinator_data(value)
        if self.entity_description.update_method_name:
            self._attr_is_on = bool(self._attr_native_value)


async_setup_entry = make_platform_async_setup_entry(
    ENTITY_DESCRIPTIONS, Picaso3DSwitch, _LOGGER
)
