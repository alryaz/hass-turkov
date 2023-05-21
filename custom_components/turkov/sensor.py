"""Platform for the Turkov sensor component."""

import logging
from typing import Dict

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfLength,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TurkovDeviceUpdateCoordinator
from .const import DOMAIN, CLIMATE_ATTRS
from .entity import TurkovEntity

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    # SensorEntityDescription(
    #     key="fan_speed",
    #     state_class=SensorStateClass.MEASUREMENT,
    #     icon="mdi:fan",
    # ),
    # SensorEntityDescription(
    #     key="fan_mode",
    #     state_class=SensorStateClass.MEASUREMENT,
    #     icon="mdi:fan",
    # ),
    SensorEntityDescription(
        key="target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="outdoor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="indoor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="filter_life_percentage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:air-filter",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Turkov sensors."""
    turkov_update_coordinators: Dict[str, TurkovDeviceUpdateCoordinator] = hass.data[
        DOMAIN
    ][entry.entry_id]

    add_entities = []
    for (
        turkov_device_identifier,
        turkov_device_coordinator,
    ) in turkov_update_coordinators.items():
        add_keys = set(
            turkov_device_coordinator.turkov_device.ATTRIBUTE_KEY_MAPPING.keys()
        )

        if add_keys.issuperset(CLIMATE_ATTRS):
            add_keys.difference_update(CLIMATE_ATTRS)

        for description in SENSOR_TYPES:
            if description.key in add_keys:
                add_entities.append(
                    TurkovSensor(
                        turkov_device_coordinator=turkov_device_coordinator,
                        turkov_device_identifier=turkov_device_identifier,
                        description=description,
                    )
                )

    async_add_entities(add_entities, update_before_add=False)


class TurkovSensor(TurkovEntity, SensorEntity):
    """Representation of a Turkov sensor."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attr_unique_id = "sensor__" + self._attr_unique_id

    @callback
    def _update_attr(self) -> None:
        """Handle updated data from the coordinator."""
        super()._update_attr()
        if self._attr_available:
            self._attr_native_value = getattr(
                self.coordinator.turkov_device, self.entity_description.key
            )
