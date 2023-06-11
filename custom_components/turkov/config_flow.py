"""Config flow for Turkov integration."""

import logging
from typing import Any, Optional, Dict

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_VERIFY_SSL,
    CONF_HOSTS,
    CONF_HOST,
    CONF_METHOD,
)
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import TurkovAPI, TurkovAPIError
from .api import TurkovAPIAuthenticationError, TurkovDevice
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_METHOD): vol.In(
            {
                CONF_EMAIL: "E-Mail (Cloud & Local)",
                CONF_HOST: "Host (Local only)",
            }
        )
    }
)

STEP_EMAIL_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_VERIFY_SSL, default=True): bool,
    }
)

STEP_CLOUD_HOST_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_HOST): str,
    }
)

STEP_HOST_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Turkov."""

    VERSION = 1

    def __init__(self) -> None:
        self._current_config: Dict[str, Any] = {}
        self._devices: Optional[Dict[str, TurkovDevice]] = None
        self._current_serial_number: Optional[str] = None

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle initial step (method selection)"""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        if user_input[CONF_METHOD] == CONF_EMAIL:
            return await self.async_step_email()
        if user_input[CONF_METHOD] == CONF_HOST:
            return await self.async_step_host()
        return self.async_abort("invalid_data")

    async def async_step_email(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle E-mail method step"""
        if user_input is None:
            return self.async_show_form(
                step_id="email", data_schema=STEP_EMAIL_DATA_SCHEMA
            )

        errors = {}

        turkov_api = TurkovAPI(
            async_get_clientsession(self.hass, verify_ssl=user_input[CONF_VERIFY_SSL]),
            user_input[CONF_EMAIL],
            user_input[CONF_PASSWORD],
        )

        # noinspection PyBroadException
        try:
            await turkov_api.authenticate()
            await turkov_api.update_user_data()
        except aiohttp.ClientError as exc:
            _LOGGER.error(f"Connection error: {exc}")
            errors["base"] = "cannot_connect"
        except TurkovAPIAuthenticationError as exc:
            _LOGGER.error(f"Authentication error: {exc}")
            errors["base"] = "invalid_auth"
        except TurkovAPIError as exc:
            _LOGGER.error(f"Connection error: {exc}")
            errors["base"] = "cannot_connect"
        except BaseException:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            self._current_config.update(user_input)
            self._devices = {
                device.serial_number: device
                for device in turkov_api.devices.values()
                if device.serial_number
            }
            return await self.async_step_cloud_host()

        return self.async_show_form(
            step_id="email",
            data_schema=self.add_suggested_values_to_schema(
                STEP_EMAIL_DATA_SCHEMA,
                {
                    CONF_EMAIL: user_input[CONF_EMAIL],
                    CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                },
            ),
            errors=errors,
        )

    async def async_step_cloud_host(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle local control setup for E-mail configurations."""
        errors = {}

        current_serial_number: Optional[str] = self._current_serial_number
        if user_input is None or not current_serial_number:
            try:
                current_serial_number = next(iter(self._devices))
            except (AttributeError, StopIteration):
                # Check for both _devices being None or empty
                pass
        else:
            device_hosts: Dict[str, str] = self._current_config.setdefault(
                CONF_HOSTS, {}
            )

            current_device = self._devices[current_serial_number]
            host = user_input.get(CONF_HOST)
            try:
                if host:
                    current_device.host = host
                    await current_device.get_state_local()
                    device_hosts[current_serial_number] = host
                else:
                    del self._devices[current_serial_number]

            except TurkovAPIError:
                current_device.host = None
                errors["base"] = "cannot_connect"
            else:
                self._current_serial_number = (current_serial_number := None)
                for serial_number in self._devices:
                    if serial_number not in device_hosts:
                        current_serial_number = serial_number
                        break

        if current_serial_number is None:
            config = self._current_config

            await self.async_set_unique_id(f"cloud__{config[CONF_EMAIL]}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=config[CONF_EMAIL],
                data=config,
            )

        current_device = self._devices[current_serial_number]
        self._current_serial_number = current_serial_number
        return self.async_show_form(
            step_id="cloud_host",
            errors=errors,
            data_schema=STEP_CLOUD_HOST_DATA_SCHEMA,
            description_placeholders={
                "device__serial_number": current_serial_number,
                "device__name": current_device.name or "<...>",
                "device__type": current_device.type or "<...>",
            },
        )

    async def async_step_host(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="host", data_schema=STEP_HOST_DATA_SCHEMA
            )

        errors = {}

        device = TurkovDevice(
            host=(host := user_input[CONF_HOST]),
            session=async_get_clientsession(self.hass),
        )

        try:
            await device.get_state()
        except (TurkovAPIError, aiohttp.ClientError) as exc:
            _LOGGER.error(f"Connection error: {exc}", exc_info=exc)
            errors["base"] = "cannot_connect"
        else:
            await self.async_set_unique_id(f"device__{host}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=host,
                data={CONF_HOST: host},
            )

        return self.async_show_form(
            step_id="host",
            errors=errors,
            data_schema=self.add_suggested_values_to_schema(
                STEP_CLOUD_HOST_DATA_SCHEMA,
                {CONF_HOST: host},
            ),
        )
