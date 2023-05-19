"""Support for Turkov climate."""
from typing import Any, Dict, ClassVar

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
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
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

    FAN_MODE_TO_DEVICE_MAPPING: ClassVar[Dict[str, str]] = {
        "0": FAN_OFF,
        "A": FAN_AUTO,
        "1": FAN_LOW,
        "2": FAN_MEDIUM,
        "3": FAN_HIGH,
    }

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
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

        if self._attr_hvac_modes is None:
            self._attr_hvac_modes = (hvac_modes := [HVACMode.OFF, HVACMode.FAN_ONLY])

            if device.has_heater:
                hvac_modes.insert(1, HVACMode.HEAT)

        if self._attr_fan_modes is None:
            self._attr_fan_modes = (fan_modes := [FAN_LOW, FAN_MEDIUM, FAN_HIGH])

            if device.fan_mode == "both":
                fan_modes.insert(0, FAN_AUTO)

        self._attr_hvac_mode = (
            (HVACMode.HEAT if device.is_heater_on else HVACMode.FAN_ONLY)
            if device.is_on
            else HVACMode.OFF
        )
        self._attr_fan_mode = self.FAN_MODE_TO_DEVICE_MAPPING.get(
            device.fan_speed, FAN_AUTO
        )

    async def async_turn_on(self) -> None:
        coordinator = self.coordinator

        # Device call
        await coordinator.turkov_device.turn_on()

        # Refresh call
        await coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        coordinator = self.coordinator

        # Device call
        await coordinator.turkov_device.turn_off()

        # Refresh call
        await coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        coordinator = self.coordinator
        device = coordinator.turkov_device

        try:
            fan_speed_value = list(self.FAN_MODE_TO_DEVICE_MAPPING.keys())[
                list(self.FAN_MODE_TO_DEVICE_MAPPING.values()).index(fan_mode)
            ]
        except ValueError:
            raise HomeAssistantError(f"Fan mode {fan_mode} not found in mapping")

        # Device calls
        await device.turn_on()
        await device.set_fan_speed(fan_speed_value)

        # Refresh call
        await coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        if (hvac_modes := self._attr_hvac_modes) is None:
            raise HomeAssistantError("HVAC modes not yet loaded")
        if hvac_mode not in hvac_modes:
            raise ValueError("HVAC mode not supported")

        coordinator = self.coordinator
        device = coordinator.turkov_device

        # Device calls
        if hvac_mode == HVACMode.OFF:
            await device.turn_off()
        else:
            if not device.is_on:
                await device.turn_on()
            if hvac_mode == HVACMode.HEAT:
                await device.turn_on_heater()
            elif hvac_mode == HVACMode.FAN_ONLY:
                await device.turn_off_heater()

        # Refresh call
        await coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            raise ValueError(f"Missing parameter {ATTR_TEMPERATURE}")

        coordinator = self.coordinator
        device = coordinator.turkov_device

        if not hasattr(device, CLIMATE_ATTR_TARGET_TEMPERATURE):
            raise HomeAssistantError(
                "Device does not support setting target temperature"
            )

        # Device calls
        await device.turn_on()
        await device.turn_on_heater()
        await device.set_target_temperature(kwargs[ATTR_TEMPERATURE])

        # Refresh call
        await coordinator.async_request_refresh()
