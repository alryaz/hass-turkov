"""Entity for the Turkov component."""
from dataclasses import dataclass
from typing import Optional

from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.entity_platform import async_get_current_platform
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TurkovDeviceUpdateCoordinator
from .api import TurkovAPI
from .const import DOMAIN


@dataclass
class TurkovEntityDescription(EntityDescription):
    """Base class for Turkov entity descriptions."""

    name_source: Optional[str] = None
    has_entity_name: bool = True
    value_source: Optional[str] = None

    def __post_init__(self) -> None:
        """Set default translation key."""
        if not self.translation_key:
            self.translation_key = self.key
        if not self.value_source:
            self.value_source = self.key


class TurkovEntity(CoordinatorEntity[TurkovDeviceUpdateCoordinator]):
    """Representation of a Turkov entity."""

    entity_description: Optional[TurkovEntityDescription]

    def __init__(
        self,
        turkov_device_coordinator: TurkovDeviceUpdateCoordinator,
        turkov_device_identifier: str,
        entity_description: Optional[TurkovEntityDescription] = None,
        enabled_default: bool = True,
    ) -> None:
        """Initialize the entity."""
        super().__init__(turkov_device_coordinator)

        self._turkov_device_identifier = turkov_device_identifier

        self.entity_description = entity_description
        self._attr_entity_registry_enabled_default = enabled_default

        unique_id_parts = [
            async_get_current_platform().domain,
            turkov_device_identifier,
        ]
        if entity_description is not None:
            unique_id_parts.append(entity_description.key)

        self._attr_unique_id = "__".join(unique_id_parts)
        self._update_attr()

    @property
    def device_name(self) -> str:
        turkov_device = self.coordinator.turkov_device
        return (
            turkov_device.name
            or turkov_device.type
            or self._turkov_device_identifier
        )

    def _update_attr(self) -> None:
        """Update attributes on entity"""
        if source := self.entity_description.name_source:
            self._attr_name = (
                getattr(self.coordinator.turkov_device, source, None)
                or self.entity_description.name
            )

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
            configuration_url=(device.api or TurkovAPI).BASE_URL,
            identifiers={(DOMAIN, self._turkov_device_identifier)},
            manufacturer="Turkov",
            model=device.type,
            name=self.device_name,
            sw_version=device.firmware_version,
        )
