"""Platform for the Turkov sensor component."""

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfPressure,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TurkovDeviceUpdateCoordinator
from .const import DOMAIN, CONF_ENABLE_ALL_ENTITIES
from .entity import TurkovEntity

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="outdoor_temperature",
        name="Outdoor Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        has_entity_name=True,
        translation_key="outdoor_temperature",
    ),
    SensorEntityDescription(
        key="filter_life_percentage",
        name="Filter Used Percentage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:air-filter",
        has_entity_name=True,
        translation_key="filter_life_percentage",
    ),
    SensorEntityDescription(
        key="air_pressure",
        name="Air Pressure",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.PA,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        has_entity_name=True,
        translation_key="air_pressure",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Turkov sensors."""
    turkov_update_coordinators: dict[
        str, TurkovDeviceUpdateCoordinator
    ] = hass.data[DOMAIN][entry.entry_id]

    add_entities = []
    for (
        identifier,
        coordinator,
    ) in turkov_update_coordinators.items():
        add_keys = set(coordinator.turkov_device.ATTRIBUTE_KEY_MAPPING.keys())
        _LOGGER.debug(f"{identifier} host config {coordinator.host_config}")
        add_all_entities = coordinator.host_config[CONF_ENABLE_ALL_ENTITIES]

        for description in SENSOR_TYPES:
            add_entity = (
                description.key in add_keys
                and getattr(
                    coordinator.turkov_device,
                    description.key,
                    None,
                )
                is not None
            )
            if not (add_entity or add_all_entities):
                continue
            add_entities.append(
                TurkovSensor(
                    turkov_device_coordinator=coordinator,
                    turkov_device_identifier=identifier,
                    description=description,
                    enabled_default=add_entity,
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
