"""The Turkov integration."""
import asyncio
import logging
from datetime import timedelta
from typing import Set

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_VERIFY_SSL,
    CONF_ACCESS_TOKEN,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import update_coordinator
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import TurkovAPI, TurkovAPIError, TurkovDevice
from .const import (
    DOMAIN,
    CONF_ACCESS_TOKEN_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_REFRESH_TOKEN_EXPIRES_AT,
)

_LOGGER = logging.getLogger(__name__)

# PLATFORMS = (Platform.BINARY_SENSOR, Platform.SENSOR)
PLATFORMS = (Platform.SENSOR, Platform.CLIMATE)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Turkov from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    turkov_api_connection = TurkovAPI(
        async_get_clientsession(hass, entry.data[CONF_VERIFY_SSL]),
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        access_token=entry.data.get(CONF_ACCESS_TOKEN),
        access_token_expires_at=entry.data.get(CONF_ACCESS_TOKEN_EXPIRES_AT),
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
        refresh_token_expires_at=entry.data.get(CONF_REFRESH_TOKEN_EXPIRES_AT),
    )

    await turkov_api_connection.update_user_data(True)

    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_ACCESS_TOKEN: turkov_api_connection.access_token,
            CONF_ACCESS_TOKEN_EXPIRES_AT: turkov_api_connection.access_token_expires_at,
            CONF_REFRESH_TOKEN: turkov_api_connection.refresh_token,
            CONF_REFRESH_TOKEN_EXPIRES_AT: turkov_api_connection.refresh_token_expires_at,
        },
    )

    turkov_device_coordinators = {
        turkov_device_id: TurkovDeviceUpdateCoordinator(
            hass,
            turkov_device=turkov_device,
        )
        for turkov_device_id, turkov_device in turkov_api_connection.devices.items()
    }

    hass.data[DOMAIN][entry.entry_id] = turkov_device_coordinators

    initial_update_tasks = {
        turkov_device_id: hass.loop.create_task(
            turkov_device_coordinator.async_config_entry_first_refresh()
        )
        for turkov_device_id, turkov_device_coordinator in turkov_device_coordinators.items()
    }
    await asyncio.wait(initial_update_tasks.values(), return_when=asyncio.ALL_COMPLETED)

    for turkov_device_id, task in initial_update_tasks.items():
        if exc := task.exception():
            _LOGGER.error(
                f"Failed updating device {turkov_device_id}: {exc}", exc_info=exc
            )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class TurkovDeviceUpdateCoordinator(DataUpdateCoordinator[Set[str]]):
    """Class to manage fetching Turkov data."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        turkov_device: TurkovDevice,
    ) -> None:
        """Initialize Turkov per-device data updater."""
        self.turkov_device = turkov_device

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )

    async def _async_update_data(self) -> Set[str]:
        """Fetch data."""
        try:
            return await self.turkov_device.update_state()
        except asyncio.CancelledError:
            raise
        except BaseException as e:
            raise update_coordinator.UpdateFailed(
                f"Unable to fetch data for Turkov device: {e}"
            )