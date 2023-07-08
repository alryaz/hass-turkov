"""Support for Turkov climate."""
from dataclasses import dataclass
from typing import Any, Dict, Final

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_HIGH,
    FAN_AUTO,
    FAN_OFF,
    ClimateEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TurkovDeviceUpdateCoordinator
from .const import DOMAIN
from .entity import TurkovEntity, TurkovEntityDescription


@dataclass
class TurkovClimateEntityDescription(
    TurkovEntityDescription, ClimateEntityDescription
):
    """Base class for Turkov climate entity description"""


CLIMATE_TYPE: Final = TurkovClimateEntityDescription(
    key="climate",
    name=None,
    has_entity_name=True,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Turkov climate."""
    turkov_update_coordinators: Dict[
        str, TurkovDeviceUpdateCoordinator
    ] = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            TurkovClimateEntity(
                turkov_device_coordinator=turkov_device_coordinator,
                turkov_device_identifier=turkov_device_identifier,
                entity_description=CLIMATE_TYPE,
            )
            for (
                turkov_device_identifier,
                turkov_device_coordinator,
            ) in turkov_update_coordinators.items()
        ],
        False,
    )


class TurkovClimateEntity(TurkovEntity, ClimateEntity):
    """BAF climate auto comfort."""

    entity_description: TurkovClimateEntityDescription

    _attr_supported_features = ClimateEntityFeature.FAN_MODE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1.0
    _attr_min_temp = 5
    _attr_max_temp = 40

    @callback
    def _update_attr_supported_features(self) -> None:
        """Calculate and update available features."""
        device = self.coordinator.turkov_device

        supported_features = ClimateEntityFeature.FAN_MODE
        if getattr(self, "_attr_supported_features", None):
            supported_features |= self._attr_supported_features
        if device.target_temperature is not None:
            supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
        if device.target_humidity is not None:
            supported_features |= ClimateEntityFeature.TARGET_HUMIDITY
        self._attr_supported_features = supported_features

    @callback
    def _update_attr_temperature(self) -> None:
        device = self.coordinator.turkov_device

        self._attr_target_temperature = device.target_temperature
        self._attr_current_temperature = (
            device.indoor_temperature
            if device.current_temperature is None
            else device.current_temperature
        )

    @callback
    def _update_attr_humidity(self) -> None:
        device = self.coordinator.turkov_device

        self._attr_target_humidity = device.target_humidity
        self._attr_current_humidity = (
            device.indoor_humidity
            if device.current_humidity is None
            else device.current_humidity
        )

    @callback
    def _update_attr_hvac(self) -> None:
        """Calculate and update available HVAC modes and state."""
        device = self.coordinator.turkov_device

        # Calculate HVAC modes
        hvac_modes = {HVACMode.OFF}
        if getattr(self, "_attr_hvac_modes", None):
            hvac_modes.update(self._attr_hvac_modes)
        if device.has_heater:
            hvac_modes.add(HVACMode.HEAT)
        if device.has_cooler:
            hvac_modes.add(HVACMode.COOL)
        if device.has_heater or device.has_cooler:
            hvac_modes.add(HVACMode.FAN_ONLY)
        if device.target_humidity is not None:
            hvac_modes.add(HVACMode.DRY)
        self._attr_hvac_modes = list(hvac_modes)

        # Calculate current HVAC mode
        self._attr_hvac_mode = (
            (
                HVACMode.DRY
                if HVACMode.DRY in hvac_modes
                else HVACMode.HEAT
                if device.is_heater_on
                else HVACMode.COOL
                if device.is_cooler_on
                else HVACMode.FAN_ONLY
            )
            if device.is_on
            else HVACMode.OFF
        )

    @callback
    def _update_attr_fan(self) -> None:
        """Calculate and update available fan modes and state."""
        device = self.coordinator.turkov_device

        # Calculate fan modes
        fan_modes = {FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_OFF}
        if getattr(self, "_attr_fan_modes", None):
            fan_modes.update(self._attr_fan_modes)
        if device.fan_mode == "both":
            fan_modes.add(FAN_AUTO)
        self._attr_fan_modes = list(fan_modes)

        # Calculate current fan mode
        if (fan_speed := device.fan_speed) == "auto":
            self._attr_fan_mode = FAN_AUTO
        elif fan_speed in ("1", "2", "3"):
            self._attr_fan_mode = (FAN_LOW, FAN_MEDIUM, FAN_HIGH)[
                int(fan_speed) - 1
            ]
        else:
            self._attr_fan_mode = FAN_OFF

    @callback
    def _update_attr_picture(self) -> None:
        """Update entity picture."""
        device = self.coordinator.turkov_device
        self._attr_entity_picture = (
            device.image_url or self._attr_entity_picture
        )

    @callback
    def _update_attr(self) -> None:
        super()._update_attr()

        self._update_attr_picture()
        self._update_attr_supported_features()
        self._update_attr_temperature()
        self._update_attr_humidity()
        self._update_attr_hvac()
        self._update_attr_fan()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        coordinator = self.coordinator
        device = coordinator.turkov_device

        if fan_mode == FAN_OFF:
            # Handle virtual fan off mode
            if device.is_on:
                await device.turn_off()

        else:
            # Handle all other existing modes
            if fan_mode == FAN_AUTO:
                fan_speed_value = "auto"
            elif fan_mode in (FAN_LOW, FAN_MEDIUM, FAN_HIGH):
                fan_speed_value = str(
                    (FAN_LOW, FAN_MEDIUM, FAN_HIGH).index(fan_mode) + 1
                )
            else:
                raise ValueError(f"Fan mode {fan_mode} not found in mapping")

            # Device calls
            if not device.is_on:
                await device.turn_on()
            await device.set_fan_speed(fan_speed_value)

        # Refresh call
        await coordinator.async_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        if hvac_mode not in getattr(self, "_attr_hvac_modes", ()):
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
            if hvac_mode == HVACMode.FAN_ONLY:
                # @TODO: handle dryer?
                if device.is_heater_on or device.is_cooler_on:
                    await device.turn_off_hvac()
            elif hvac_mode == HVACMode.DRY:
                # @TODO: check whether this is enough
                await device.set_target_humidity(self._attr_target_humidity)
            else:
                if hvac_mode == HVACMode.HEAT:
                    if not device.is_heater_on:
                        await device.turn_on_heater()
                elif hvac_mode == HVACMode.COOL:
                    if not device.is_cooler_on:
                        await device.turn_on_cooler()
                else:
                    raise ValueError("unsupported HVAC mode")
                # Send target temperature because turn off resets heater
                await device.set_target_temperature(
                    self._attr_target_temperature
                )

        # Refresh call
        await coordinator.async_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            raise ValueError(f"Missing parameter {ATTR_TEMPERATURE}")

        coordinator = self.coordinator
        device = coordinator.turkov_device

        # Device calls
        if not device.is_on:
            await device.turn_on()
        if not device.is_heater_on:
            await device.turn_on_heater()
        await device.set_target_temperature(kwargs[ATTR_TEMPERATURE])

        # Refresh call
        await coordinator.async_refresh()

    async def async_set_humidity(self, humidity: int) -> None:
        """Set the target humidity"""
        coordinator = self.coordinator
        device = coordinator.turkov_device

        if not device.is_on:
            await device.turn_on()
        await device.set_target_humidity(humidity)

        # Refresh call
        await coordinator.async_refresh()
