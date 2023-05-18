"""Support for Turkov climate."""
from typing import Any, Dict, ClassVar, List

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_HIGH,
    FAN_AUTO,
    FAN_OFF,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TurkovDeviceUpdateCoordinator
from .const import (
    DOMAIN,
    CLIMATE_ATTRS,
    CLIMATE_ATTR_CURRENT_TEMPERATURE,
    CLIMATE_ATTR_TARGET_TEMPERATURE,
)
from .entity import TurkovEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Turkov climate."""
    turkov_update_coordinators: Dict[str, TurkovDeviceUpdateCoordinator] = hass.data[
        DOMAIN
    ][entry.entry_id]

    async_add_entities(
        [
            TurkovClimateEntity(turkov_update_coordinator)
            for (
                turkov_device_id,
                turkov_update_coordinator,
            ) in turkov_update_coordinators.items()
            if CLIMATE_ATTRS.issubset(
                turkov_update_coordinator.turkov_device.ATTRIBUTE_KEY_MAPPING
            )
        ],
        False,
    )


class TurkovClimateEntity(TurkovEntity, ClimateEntity):
    """BAF climate auto comfort."""

    FAN_MODES_MAPPING: ClassVar[Dict[str, str]] = {
        "0": FAN_OFF,
        "A": FAN_AUTO,
        "1": FAN_LOW,
        "2": FAN_MEDIUM,
        "3": FAN_HIGH,
    }

    FAN_MODES_MANUAL: ClassVar[List[str]] = [FAN_LOW, FAN_MEDIUM, FAN_HIGH]
    FAN_MODES_WITH_AUTO: ClassVar[List[str]] = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.AUX_HEAT
        | ClimateEntityFeature.FAN_MODE
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.FAN_ONLY]
    # _attr_fan_modes = [FAN_LOW, FAN_MEDIUM, FAN_HIGH]
    _attr_target_temperature_step = 1.0

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attr_unique_id = "climate__" + self._attr_unique_id

    @callback
    def _update_attr(self) -> None:
        super()._update_attr()
        device = self.coordinator.turkov_device
        self._attr_entity_picture = device.image_url or self._attr_entity_picture
        self._attr_target_temperature = getattr(device, CLIMATE_ATTR_TARGET_TEMPERATURE)
        self._attr_current_temperature = getattr(
            device, CLIMATE_ATTR_CURRENT_TEMPERATURE
        )
        self._attr_hvac_mode = HVACMode.FAN_ONLY if device.is_on else HVACMode.OFF
        self._attr_fan_modes = (
            self.FAN_MODES_WITH_AUTO
            if device.fan_mode == "both"
            else self.FAN_MODES_MANUAL
        )
        self._attr_fan_mode = self.FAN_MODES_MAPPING.get(device.fan_speed, FAN_AUTO)
        self._attr_is_aux_heat = True  # @TODO

    async def async_turn_on(self) -> None:
        pass

    async def async_turn_off(self) -> None:
        pass

    async def async_turn_aux_heat_on(self) -> None:
        pass

    async def async_turn_aux_heat_off(self) -> None:
        pass

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        pass

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        pass
