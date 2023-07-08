"""Platform for the Turkov switch component."""
import asyncio
import logging
from dataclasses import dataclass
from functools import partial
from typing import Callable, Awaitable, Optional, Any

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.core import callback

from . import TurkovDevice
from .entity import TurkovEntity, TurkovEntityDescription
from .helpers import async_setup_entry_for_platform

_LOGGER = logging.getLogger(__name__)


# noinspection PyUnusedLocal
def _raise_not_implemented(*args, **kwargs):
    raise NotImplementedError


@dataclass
class TurkovSwitchEntityDescription(
    TurkovEntityDescription, SwitchEntityDescription
):
    """Base class for Turkov switches."""

    command_on: Callable[[TurkovDevice], Awaitable] = _raise_not_implemented
    command_off: Callable[[TurkovDevice], Awaitable] = _raise_not_implemented
    icon_on: Optional[str] = None


ENTITY_TYPES: tuple[TurkovSwitchEntityDescription, ...] = (
    TurkovSwitchEntityDescription(
        key="first_relay",
        name="First Relay",
        name_source="first_relay_name",
        icon="mdi:electric-switch",
        icon_on="mdi:electric-switch-closed",
        command_on=lambda x: x.turn_on_first_relay,
        command_off=lambda x: x.turn_off_first_relay,
    ),
    TurkovSwitchEntityDescription(
        key="second_relay",
        name="Second Relay",
        name_source="second_relay_name",
        icon="mdi:electric-switch",
        icon_on="mdi:electric-switch-closed",
        command_on=lambda x: x.turn_on_second_relay,
        command_off=lambda x: x.turn_off_second_relay,
    ),
    TurkovSwitchEntityDescription(
        key="fireplace",
        name="Fireplace",
        icon="mdi:fireplace-off",
        icon_on="mdi:fireplace",
        command_on=lambda x: x.turn_on_fireplace,
        command_off=lambda x: x.turn_off_fireplace,
    ),
    TurkovSwitchEntityDescription(
        key="humidifier",
        name="Humidifier",
        icon="mdi:humidifier-off",
        icon_on="mdi:humidifier",
        command_on=lambda x: x.turn_on_humidifier,
        command_off=lambda x: x.turn_off_humidifier,
    ),
)


class TurkovSwitch(TurkovEntity, SwitchEntity):
    """Representation of a Turkov switch."""

    entity_description: TurkovSwitchEntityDescription

    @callback
    def _update_attr(self) -> None:
        """Handle updated data from the coordinator."""
        super()._update_attr()

        state = getattr(
            self.coordinator.turkov_device,
            self.entity_description.value_source,
        )

        if state is None:
            self._attr_assumed_state = True
            self._attr_is_on = None
            self._attr_icon = self.entity_description.icon
        else:
            self._attr_assumed_state = False
            self._attr_is_on = bool(state)
            self._attr_icon = (
                self.entity_description.icon_on
                if self._attr_is_on
                else self.entity_description.icon
            )

    async def async_turn_on(self, **kwargs) -> None:
        """Proxy method to run enable boolean command."""
        await self.entity_description.command_on(
            self.coordinator.turkov_device
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Proxy method to run disable boolean command."""
        await self.entity_description.command_on(
            self.coordinator.turkov_device
        )
        await self.coordinator.async_request_refresh()

    def turn_on(self, **kwargs: Any) -> None:
        """Compatibility for synchronous turn on calls."""
        asyncio.run_coroutine_threadsafe(
            self.async_turn_on(**kwargs), self.hass.loop
        ).result()

    def turn_off(self, **kwargs: Any) -> None:
        """Compatibility for synchronous turn off calls."""
        asyncio.run_coroutine_threadsafe(
            self.async_turn_off(**kwargs), self.hass.loop
        ).result()


async_setup_entry = partial(
    async_setup_entry_for_platform, _LOGGER, ENTITY_TYPES, TurkovSwitch
)
