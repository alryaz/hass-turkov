"""Platform for the Turkov sensor component."""

import logging
from dataclasses import dataclass
from functools import partial

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfPressure,
)
from homeassistant.core import callback

from .entity import TurkovEntity, TurkovEntityDescription
from .helpers import async_setup_entry_for_platform

_LOGGER = logging.getLogger(__name__)


@dataclass
class TurkovSensorEntityDescription(
    TurkovEntityDescription, SensorEntityDescription
):
    """Base class for Turkov sensors."""


ENTITY_TYPES: tuple[TurkovSensorEntityDescription, ...] = (
    TurkovSensorEntityDescription(
        key="outdoor_temperature",
        name="Outdoor Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    TurkovSensorEntityDescription(
        key="filter_life_percentage",
        name="Filter Used Percentage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:air-filter",
    ),
    TurkovSensorEntityDescription(
        key="air_pressure",
        name="Air Pressure",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.PA,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
)


class TurkovSensor(TurkovEntity, SensorEntity):
    """Representation of a Turkov sensor."""

    entity_description: TurkovSensorEntityDescription

    @callback
    def _update_attr(self) -> None:
        """Handle updated data from the coordinator."""
        super()._update_attr()
        if self._attr_available:
            self._attr_native_value = getattr(
                self.coordinator.turkov_device, self.entity_description.key
            )


async_setup_entry = partial(
    async_setup_entry_for_platform, _LOGGER, ENTITY_TYPES, TurkovSensor
)
