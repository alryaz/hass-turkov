"""Entity for the Turkov component."""
from typing import Optional

from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TurkovDeviceUpdateCoordinator
from .const import DOMAIN


class TurkovEntity(CoordinatorEntity[TurkovDeviceUpdateCoordinator]):
    """Representation of a Turkov entity."""

    def __init__(
        self,
        turkov_device_coordinator: TurkovDeviceUpdateCoordinator,
        description: Optional[EntityDescription] = None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(turkov_device_coordinator)

        self._device_id = turkov_device_coordinator.turkov_device.id

        if description is not None:
            self.entity_description = description
            self._attr_unique_id = f"{self._device_id}_{description.key}"
        else:
            self._attr_unique_id = self._device_id

        self._update_attr()

    @property
    def device_name(self) -> str:
        turkov_device = self.coordinator.turkov_device
        return turkov_device.device_name or turkov_device.device_type or self._device_id

    @callback
    def _update_attr(self) -> None:
        """Update the state and attributes."""
        name = self.device_name
        if desc := getattr(self, "entity_description", None):
            name += " " + (desc.name or desc.key.replace("_", " ").title())
            self._attr_available = (
                getattr(self.coordinator.turkov_device, desc.key, None) is not None
            )

        self._attr_name = name

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attr()
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device_info of the device."""
        device = self.coordinator.turkov_device
        return DeviceInfo(
            configuration_url=device.api.BASE_URL,
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Turkov",
            model=device.device_type,
            name=self.device_name,
            sw_version=device.firmware_version,
        )
