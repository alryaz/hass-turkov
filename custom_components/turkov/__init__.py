"""The Turkov integration."""
import asyncio
import logging
from copy import deepcopy
from datetime import timedelta
from typing import Set, Dict, Any, Final

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_EMAIL,
    CONF_ACCESS_TOKEN,
    Platform,
    CONF_HOST,
    CONF_HOSTS,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import update_coordinator
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
from .helpers import (
    HOST_OPTIONS_SCHEMA,
    CLOUD_OPTIONS_SCHEMA,
    HOST_DATA_SCHEMA,
    async_get_updated_api,
)

_LOGGER: Final = logging.getLogger(__name__)

# PLATFORMS = (Platform.BINARY_SENSOR, Platform.SENSOR)
PLATFORMS = (Platform.SENSOR, Platform.CLIMATE, Platform.SWITCH)


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
        host_config = HOST_OPTIONS_SCHEMA(
            hosts.setdefault(turkov_device.id, {})
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
            host_config=HOST_DATA_SCHEMA(
                dict(entry.data),
            ),
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
        # Add ability to set options
        try:
            hosts = new_data.pop(CONF_HOSTS)
        except KeyError:
            pass
        else:
            new_hosts = new_options.setdefault(CONF_HOSTS, {})
            for serial_number, host in hosts.items():
                new_hosts[serial_number] = {CONF_HOST: host}
        entry.version = 2

    if entry.version < 3:
        # Fix missing underscore
        from homeassistant.helpers.entity_registry import (
            async_migrate_entries,
            RegistryEntry,
        )

        def _migrate_callback(ent: RegistryEntry) -> dict[str, Any] | None:
            """Add another underscore for entities."""
            if ent.domain == "sensor":
                for postfix in (
                    "air_quality",
                    "filter_life_percentage",
                    "outdoor_temperature",
                ):
                    if ent.unique_id.endswith(postfix):
                        return {
                            "new_unique_id": ent.unique_id[: -len(postfix)]
                            + "_"
                            + postfix
                        }
            elif ent.domain == "climate":
                return {"new_unique_id": ent.unique_id + "__climate"}
            else:
                return

        await async_migrate_entries(hass, entry.entry_id, _migrate_callback)
        entry.version = 3

    if entry.version < 4 and (hosts_conf := new_options.get(CONF_HOSTS)):
        turkov_api = await async_get_updated_api(hass, entry)

        for serial in tuple(hosts_conf):
            for device in turkov_api.devices.values():
                if device.serial_number == serial:
                    _LOGGER.debug(
                        f"Migrating host keying {serial} to {device.id}"
                    )
                    hosts_conf[device.id] = hosts_conf.pop(serial)
                    break
            if serial in hosts_conf:
                _LOGGER.warning(
                    f"Configuration for device with serial number {serial} lost due to missing device"
                )
                del hosts_conf[serial]
        entry.version = 4

    # Apply on every migration
    args["options"] = (
        CLOUD_OPTIONS_SCHEMA if CONF_EMAIL in new_data else HOST_OPTIONS_SCHEMA
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
