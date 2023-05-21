"""Support for Turkov climate."""
from typing import Any, Dict, ClassVar, Optional

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
    CLIMATE_ATTR_FAN_MODE,
    CLIMATE_ATTR_TARGET_HUMIDITY,
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
            TurkovClimateEntity(
                turkov_device_coordinator=turkov_device_coordinator,
                turkov_device_identifier=turkov_device_identifier,
            )
            for (
                turkov_device_identifier,
                turkov_device_coordinator,
            ) in turkov_update_coordinators.items()
            if CLIMATE_ATTRS.issubset(
                turkov_device_coordinator.turkov_device.ATTRIBUTE_KEY_MAPPING
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

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1.0
    _attr_min_temp = 5
    _attr_max_temp = 40

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attr_unique_id = "climate__" + self._attr_unique_id
        self._has_real_fan_off = False

    @callback
    def _update_attr_supported_features(self) -> None:
        """Calculate and update available features."""
        device = self.coordinator.turkov_device
        supported_features = ClimateEntityFeature(0)

        if getattr(device, CLIMATE_ATTR_TARGET_TEMPERATURE, None) is not None:
            supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE

        if getattr(device, CLIMATE_ATTR_TARGET_HUMIDITY, None) is not None:
            supported_features |= ClimateEntityFeature.TARGET_HUMIDITY

        if getattr(device, CLIMATE_ATTR_FAN_MODE, None) is not None:
            supported_features |= ClimateEntityFeature.FAN_MODE

        self._attr_supported_features = supported_features

    @callback
    def _update_attr_temperature(self) -> None:
        device = self.coordinator.turkov_device

        self._attr_target_temperature = getattr(
            device, CLIMATE_ATTR_TARGET_TEMPERATURE, None
        )
        self._attr_current_temperature = getattr(
            device, CLIMATE_ATTR_CURRENT_TEMPERATURE, None
        )

    @callback
    def _update_attr_hvac(self) -> None:
        """Calculate and update available HVAC modes and state."""
        device = self.coordinator.turkov_device
        hvac_modes = [HVACMode.OFF]

        if device.has_heater:
            hvac_modes.append(HVACMode.HEAT)

        if getattr(device, CLIMATE_ATTR_FAN_MODE, None) is not None:
            hvac_modes.append(HVACMode.FAN_ONLY)

        self._attr_hvac_modes = hvac_modes

        self._attr_hvac_mode = (
            (
                HVACMode.HEAT
                if device.is_heater_on
                else HVACMode.FAN_ONLY
                if HVACMode.FAN_ONLY in hvac_modes
                else HVACMode.OFF
            )
            if device.is_on
            else HVACMode.OFF
        )

    @callback
    def _update_attr_fan(self) -> None:
        """Calculate and update available fan modes and state."""
        device = self.coordinator.turkov_device
        fan_modes = [FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_OFF]

        if device.fan_mode == "both":
            fan_modes.insert(0, FAN_AUTO)

            # @TODO: check if this is true
            self._has_real_fan_off = True
        elif device.fan_mode == "manual":
            self._has_real_fan_off = False

        self._attr_fan_modes = fan_modes

        self._attr_fan_mode = (
            self.FAN_MODE_TO_DEVICE_MAPPING.get(device.fan_speed, FAN_AUTO)
            if not self._has_real_fan_off and device.is_on
            else FAN_OFF
        )

    @callback
    def _update_attr_picture(self) -> None:
        """Update entity picture."""
        device = self.coordinator.turkov_device
        self._attr_entity_picture = device.image_url or self._attr_entity_picture

    @callback
    def _update_attr(self) -> None:
        super()._update_attr()

        self._update_attr_picture()
        self._update_attr_supported_features()
        self._update_attr_temperature()
        self._update_attr_hvac()
        self._update_attr_fan()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        coordinator = self.coordinator
        device = coordinator.turkov_device

        if not self._has_real_fan_off and fan_mode == FAN_OFF:
            if device.is_on:
                await device.turn_off()

        else:
            try:
                fan_speed_value = list(self.FAN_MODE_TO_DEVICE_MAPPING.keys())[
                    list(self.FAN_MODE_TO_DEVICE_MAPPING.values()).index(fan_mode)
                ]
            except ValueError:
                raise HomeAssistantError(f"Fan mode {fan_mode} not found in mapping")

            # Device calls
            if not device.is_on:
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
            if device.is_on:
                await device.turn_off()
        else:
            if not device.is_on:
                await device.turn_on()
            if hvac_mode == HVACMode.HEAT:
                if not device.is_heater_on:
                    await device.turn_on_heater()
                # Send target temperature because turn off resets heater
                await device.set_target_temperature(self._attr_target_temperature)
            elif hvac_mode == HVACMode.FAN_ONLY:
                if device.is_heater_on:
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
        if not device.is_on:
            await device.turn_on()
        if not device.is_heater_on:
            await device.turn_on_heater()
        await device.set_target_temperature(kwargs[ATTR_TEMPERATURE])

        # Refresh call
        await coordinator.async_request_refresh()
