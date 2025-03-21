"""Setup Sensor platform for Picaso3D."""

from __future__ import annotations

__all__ = (
    "async_setup_entry",
    "ENTITY_DESCRIPTIONS",
    "Picaso3DSensor",
    "Picaso3DSensorEntityDescription",
)

import logging
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature, PERCENTAGE, UnitOfTime

from custom_components.picaso_3d import (
    Picaso3DCoordinatorEntity,
    Picaso3DCoordinatorEntityDescription,
    make_platform_async_setup_entry,
)
from custom_components.picaso_3d.api import NetPrinterStatus, NetPrinterState, Picaso3DPrinter, StopReason, PauseReason

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class Picaso3DSensorEntityDescription(
    Picaso3DCoordinatorEntityDescription, SensorEntityDescription
):
    """Describes Picaso3D sensor entity."""


class Picaso3DSensor(
    Picaso3DCoordinatorEntity[Picaso3DSensorEntityDescription], SensorEntity
):
    """Picaso3D Sensor class."""

def _get_enum_names(enum):
    return [v.name.lower() for v in enum]


ENTITY_DESCRIPTIONS = (
    Picaso3DSensorEntityDescription(
        key="state",
        attribute="state",
        name="Printer State",
        update_method_name=Picaso3DPrinter.get_printer_state,
        device_class=SensorDeviceClass.ENUM,
        converter=lambda x: x.name.lower(),
        options=_get_enum_names(NetPrinterState),
    ),
    Picaso3DSensorEntityDescription(
        key="status",
        attribute="status",
        name="Printer Status",
        update_method_name=Picaso3DPrinter.get_printer_state,
        device_class=SensorDeviceClass.ENUM,
        converter=lambda x: x.name.lower(),
        options=[v.name.lower() for v in NetPrinterStatus],
    ),
    Picaso3DSensorEntityDescription(
        key="task_name",
        attribute="task_name",
        name="Task Name",
        update_method_name=Picaso3DPrinter.get_printer_state,
        icon="mdi:form-textbox",
    ),
    Picaso3DSensorEntityDescription(
        key="task_progress",
        attribute="task_progress",
        name="Task Progress",
        update_method_name=Picaso3DPrinter.get_printer_state,
        # device_class=SensorDeviceClass.PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    Picaso3DSensorEntityDescription(
        key="task_remaining",
        attribute="task_remaining",
        name="Task Remaining Time",
        update_method_name=Picaso3DPrinter.get_printer_state,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=1,
    ),
    Picaso3DSensorEntityDescription(
        key="first_nozzle_temperature",
        attribute="first_nozzle_temperature",
        name="Nozzle 1 Temperature",
        update_method_name=Picaso3DPrinter.get_printer_state,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    Picaso3DSensorEntityDescription(
        key="second_nozzle_temperature",
        attribute="second_nozzle_temperature",
        name="Nozzle 2 Temperature",
        update_method_name=Picaso3DPrinter.get_printer_state,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    Picaso3DSensorEntityDescription(
        key="chamber_temperature",
        attribute="chamber_temperature",
        name="Chamber Temperature",
        update_method_name=Picaso3DPrinter.get_printer_state,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    Picaso3DSensorEntityDescription(
        key="bed_temperature",
        attribute="bed_temperature",
        name="Bed Temperature",
        update_method_name=Picaso3DPrinter.get_printer_state,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    Picaso3DSensorEntityDescription(
        key="pause_reason",
        attribute="pause_reason",
        name="Pause Reason",
        converter=lambda x: (min(x).name.lower() if x else "none"),
        device_class=SensorDeviceClass.ENUM,
        options=_get_enum_names(PauseReason) + ["none"],
        update_method_name=Picaso3DPrinter.get_printer_state,
        icon=lambda x: "mdi:motion-pause-outline" if x.state == "none" else "mdi:motion-pause"
    ),
    Picaso3DSensorEntityDescription(
        key="stop_reason",
        attribute="stop_reason",
        name="Stop Reason",
        converter=lambda x: (max(x).name.lower() if x else "none"),
        device_class=SensorDeviceClass.ENUM,
        options=_get_enum_names(StopReason) + ["none"],
        update_method_name=Picaso3DPrinter.get_printer_state,
        icon=lambda x: "mdi:octagon-outline" if x.state == "none" else "mdi:close-octagon"
    ),
    # Picaso3DSensorEntityDescription(
    #     key="ready",
    #     attribute="ready",
    #     name="Ready",
    #     update_method_name=Picaso3DPrinter.get_printer_state,
    # ),
    # Picaso3DSensorEntityDescription(
    #     key="preheat_state",
    #     attribute="preheat_state",
    #     name="Preheat State",
    #     update_method_name=Picaso3DPrinter.get_printer_state,
    # ),
)

async_setup_entry = make_platform_async_setup_entry(
    ENTITY_DESCRIPTIONS, Picaso3DSensor, _LOGGER
)
