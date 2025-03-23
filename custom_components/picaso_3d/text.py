"""Text input for Picaso 3D printer."""

import logging
from dataclasses import dataclass

from homeassistant.components.text import TextEntity, TextEntityDescription
from homeassistant.const import EntityCategory

from custom_components.picaso_3d import (
    Picaso3DCoordinatorEntity,
    Picaso3DCoordinatorEntityDescription,
    TMethodName,
    make_platform_async_setup_entry,
)
from custom_components.picaso_3d.api import Picaso3DPrinter

_LOGGER = logging.getLogger(__name__)


@dataclass(kw_only=True, frozen=True)
class Picaso3DTextEntityDescription(
    Picaso3DCoordinatorEntityDescription, TextEntityDescription
):
    """Describes Picaso3D text entity."""

    set_method_name: TMethodName

    def __post_init__(self):
        super().__post_init__()
        if not isinstance(self.set_method_name, str):
            object.__setattr__(self, "set_method_name", self.set_method_name.__name__)


ENTITY_DESCRIPTIONS = [
    Picaso3DTextEntityDescription(
        key="name",
        attribute="name",
        name="Printer Name",
        update_method_name=Picaso3DPrinter.update_printer_info,
        set_method_name=Picaso3DPrinter.change_name,
        entity_category=EntityCategory.CONFIG,
    ),
]


class Picaso3DText(Picaso3DCoordinatorEntity, TextEntity):
    async def async_set_value(self, value: str) -> None:
        """Set the value of the text entity."""
        await getattr(self.printer, self.entity_description.set_method_name)(value)
        await self.coordinator.async_request_refresh()


async_setup_entry = make_platform_async_setup_entry(
    ENTITY_DESCRIPTIONS, Picaso3DText, _LOGGER
)
