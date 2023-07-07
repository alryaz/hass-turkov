"""The Turkov integration."""
import asyncio
import logging
from copy import deepcopy
from datetime import timedelta
from typing import Set, Dict, Mapping, Any, Final

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_VERIFY_SSL,
    CONF_ACCESS_TOKEN,
    Platform,
    CONF_HOST,
    CONF_HOSTS,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import update_coordinator, config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import TurkovAPI, TurkovAPIError, TurkovDevice
from .const import (
    DOMAIN,
    CONF_ACCESS_TOKEN_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_REFRESH_TOKEN_EXPIRES_AT,
    CONF_ENABLE_ALL_ENTITIES,
)

_LOGGER = logging.getLogger(__name__)

# PLATFORMS = (Platform.BINARY_SENSOR, Platform.SENSOR)
PLATFORMS = (Platform.SENSOR, Platform.CLIMATE)

STEP_EMAIL_OPTIONS_SCHEMA: Final = vol.Schema(
    {
        vol.Optional(CONF_VERIFY_SSL, default=True): cv.boolean,
    },
    extra=vol.ALLOW_EXTRA,
)
"""Schema used within cloud configuration and in options"""

STEP_EMAIL_DATA_SCHEMA: Final = vol.Schema(
    {
        vol.Required(CONF_EMAIL): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
).extend(STEP_EMAIL_OPTIONS_SCHEMA.schema)
"""Schema used for cloud configuration"""

STEP_HOST_OPTIONS_SCHEMA: Final = vol.Schema(
    {
        vol.Optional(CONF_HOST): cv.string,
        vol.Optional(CONF_ENABLE_ALL_ENTITIES, default=False): cv.boolean,
    },
    extra=vol.ALLOW_EXTRA,
)
"""Schema used within host configuration and in cloud host options"""

STEP_HOST_DATA_SCHEMA: Final = STEP_HOST_OPTIONS_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
    }
)
"""Schema used within direct host configuration and in cloud host options"""


async def async_get_updated_api(
    hass: HomeAssistant, entry: ConfigEntry | Mapping[str, Any]
) -> TurkovAPI:
    if isinstance(entry, ConfigEntry):
        entry = entry.data

    turkov_api = TurkovAPI(
        async_get_clientsession(hass, entry[CONF_VERIFY_SSL]),
        entry[CONF_EMAIL],
        entry[CONF_PASSWORD],
        access_token=entry.get(CONF_ACCESS_TOKEN),
        access_token_expires_at=entry.get(CONF_ACCESS_TOKEN_EXPIRES_AT),
        refresh_token=entry.get(CONF_REFRESH_TOKEN),
        refresh_token_expires_at=entry.get(CONF_REFRESH_TOKEN_EXPIRES_AT),
    )

    await turkov_api.update_user_data(True)

    return turkov_api


async def async_setup_email_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> Dict[str, "TurkovDeviceUpdateCoordinator"]:
    turkov_api = await async_get_updated_api(hass, entry)

    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_ACCESS_TOKEN: turkov_api.access_token,
            CONF_ACCESS_TOKEN_EXPIRES_AT: turkov_api.access_token_expires_at,
            CONF_REFRESH_TOKEN: turkov_api.refresh_token,
            CONF_REFRESH_TOKEN_EXPIRES_AT: turkov_api.refresh_token_expires_at,
        },
    )

    hosts = entry.options.get(CONF_HOSTS) or {}

    turkov_device_coordinators = {}
    for (
        turkov_device_id,
        turkov_device,
    ) in turkov_api.devices.items():
        host_config = STEP_HOST_OPTIONS_SCHEMA(
            hosts.setdefault(turkov_device.serial_number, {})
        )

        if host := host_config.get(CONF_HOST):
            turkov_device.host = host

        turkov_device_coordinators[
            turkov_device_id
        ] = TurkovDeviceUpdateCoordinator(
            hass,
            turkov_device=turkov_device,
            host_config=host_config,
        )

    return turkov_device_coordinators


async def async_setup_host_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> Dict[str, "TurkovDeviceUpdateCoordinator"]:
    turkov_device = TurkovDevice(
        session=async_get_clientsession(hass),
        host=entry.data[CONF_HOST],
    )

    await turkov_device.update_state()

    return {
        entry.data[CONF_HOST]: TurkovDeviceUpdateCoordinator(
            hass,
            turkov_device=turkov_device,
            host_config=STEP_HOST_DATA_SCHEMA(entry.options),
        )
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Turkov from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    try:
        turkov_device_coordinators = await (
            async_setup_email_entry(hass, entry)
            if CONF_EMAIL in entry.data
            else async_setup_host_entry(hass, entry)
        )
    except (TurkovAPIError, aiohttp.ClientError, TimeoutError) as exc:
        raise ConfigEntryNotReady from exc

    hass.data[DOMAIN][entry.entry_id] = turkov_device_coordinators

    initial_update_tasks = {
        identifier: hass.loop.create_task(
            turkov_device_coordinator.async_config_entry_first_refresh()
        )
        for identifier, turkov_device_coordinator in turkov_device_coordinators.items()
    }
    await asyncio.wait(
        initial_update_tasks.values(), return_when=asyncio.ALL_COMPLETED
    )

    for turkov_device_id, task in initial_update_tasks.items():
        if exc := task.exception():
            _LOGGER.error(
                f"Failed updating device {turkov_device_id}: {exc}",
                exc_info=exc,
            )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    new_data = deepcopy(dict(entry.data))
    new_options = deepcopy(dict(entry.options))
    args = {"data": new_data, "options": new_options}

    if entry.version < 2:
        try:
            hosts = new_data.pop(CONF_HOSTS)
        except KeyError:
            pass
        else:
            new_hosts = new_options.setdefault(CONF_HOSTS, {})
            for serial_number, host in hosts.items():
                new_hosts[serial_number] = {CONF_HOST: host}

    args["options"] = (
        STEP_EMAIL_OPTIONS_SCHEMA
        if CONF_EMAIL in new_data
        else STEP_HOST_DATA_SCHEMA
    )(new_options)

    hass.config_entries.async_update_entry(entry, **args)

    return True


class TurkovDeviceUpdateCoordinator(DataUpdateCoordinator[Set[str]]):
    """Class to manage fetching Turkov data."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        turkov_device: TurkovDevice,
        host_config: dict[str, Any],
    ) -> None:
        """Initialize Turkov per-device data updater."""
        self.turkov_device = turkov_device
        self.host_config = host_config

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=10),
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
            ) from e
