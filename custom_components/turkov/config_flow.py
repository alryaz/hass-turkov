"""Config flow for Turkov integration."""
import asyncio
import logging
from copy import deepcopy
from json import dumps
from typing import Any, Optional, Final

import aiohttp
from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    OptionsFlow,
    OptionsFlowWithConfigEntry,
)
from homeassistant.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_VERIFY_SSL,
    CONF_HOSTS,
    CONF_HOST,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import (
    async_get_updated_api,
    STEP_EMAIL_DATA_SCHEMA,
    STEP_HOST_OPTIONS_SCHEMA,
    STEP_HOST_DATA_SCHEMA,
    STEP_EMAIL_OPTIONS_SCHEMA,
)
from .api import TurkovAPIAuthenticationError, TurkovDevice, TurkovAPIError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Turkov."""

    VERSION = 2

    def __init__(self) -> None:
        self._devices: Optional[dict[str, TurkovDevice]] = None
        self._current_serial_number: Optional[str] = None
        self._reauth_entry: Optional[ConfigEntry] = None

        self.data: dict[str, Any] = {}
        self.options: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        """Handle initial step (method selection)"""
        if self._reauth_entry:
            return await self.async_step_email()
        return self.async_show_menu(
            step_id="user", menu_options=[CONF_EMAIL, CONF_HOST]
        )

    async def async_commit_cloud_entry(self) -> FlowResult:
        email = self.data[CONF_EMAIL]
        unique_id = f"cloud__{email}"
        if not (entry := self._reauth_entry) or entry.unique_id != unique_id:
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

        if entry:
            self.hass.config_entries.async_update_entry(
                entry,
                title=email,
                unique_id=unique_id,
                data=self.data,
                options=self.options,
            )
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        return self.async_create_entry(
            title=email, data=self.data, options=self.options
        )

    async def async_step_email(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        """Handle E-mail method step"""
        errors = {}

        if user_input is not None:
            # noinspection PyBroadException
            try:
                turkov_api = await async_get_updated_api(self.hass, user_input)
            except asyncio.CancelledError:
                raise
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
                self.data[CONF_EMAIL] = user_input[CONF_EMAIL]
                self.data[CONF_PASSWORD] = user_input[CONF_PASSWORD]
                self.options[CONF_VERIFY_SSL] = user_input[CONF_VERIFY_SSL]

                if self._reauth_entry:
                    return await self.async_commit_cloud_entry()

                self._devices = {
                    device.serial_number: device
                    for device in turkov_api.devices.values()
                    if device.serial_number
                }
                return await self.async_step_cloud_host()

        elif self._reauth_entry:
            user_input = {**self.data, **self.options}
            user_input.pop(CONF_PASSWORD, None)

        return self.async_show_form(
            step_id="email",
            data_schema=self.add_suggested_values_to_schema(
                STEP_EMAIL_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_cloud_host(
        self, user_input: dict[str, Any] | None = None
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
            device_hosts: dict[str, str] = self.data.setdefault(CONF_HOSTS, {})

            current_device = self._devices[current_serial_number]
            try:
                if host := user_input.get(CONF_HOST):
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
            return await self.async_commit_cloud_entry()

        current_device = self._devices[current_serial_number]
        self._current_serial_number = current_serial_number
        return self.async_show_form(
            step_id="cloud_host",
            errors=errors,
            data_schema=self.add_suggested_values_to_schema(
                STEP_HOST_OPTIONS_SCHEMA,
                user_input,
            ),
            description_placeholders={
                "device__serial_number": current_serial_number,
                "device__name": current_device.name or "<...>",
                "device__type": current_device.type or "<...>",
            },
        )

    async def async_step_host(
        self, user_input: dict[str, Any] | None = None
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
                STEP_HOST_DATA_SCHEMA,
                {CONF_HOST: host},
            ),
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        self.data.update(self._reauth_entry.data)
        self.options.update(self._reauth_entry.options)
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TurkovOptionsFlow(config_entry)


STEP_INIT: Final = "init"
STEP_EMAIL: Final = "email"
STEP_HOST: Final = "host"
STEP_HOSTS: Final = "hosts"
STEP_SAVE: Final = "save"


class TurkovOptionsFlow(OptionsFlowWithConfigEntry):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._current_serial: Optional[str] = None
        self._devices: Optional[dict[str, TurkovDevice]] = None
        self.initial_options = deepcopy(dict(self.config_entry.options))

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        config_entry_data = self.config_entry.data
        if CONF_HOST in config_entry_data:
            return await self.async_step_host()

        menu_options = [STEP_EMAIL, STEP_HOSTS]

        if dumps(self.options) != dumps(self.initial_options):
            menu_options.append(STEP_SAVE)

        return self.async_show_menu(
            step_id=STEP_INIT, menu_options=menu_options
        )

    async def async_step_save(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_create_entry(title="", data=self.options)

    async def async_step_email(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None:
            user_input = self.options
        else:
            self.options.update(STEP_EMAIL_OPTIONS_SCHEMA(user_input))
            return await self.async_step_init()
        return self.async_show_form(
            step_id=STEP_EMAIL,
            data_schema=self.add_suggested_values_to_schema(
                STEP_EMAIL_OPTIONS_SCHEMA, user_input
            ),
        )

    async def async_step_hosts(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        menu_options = {}
        hosts = self.options.setdefault(CONF_HOSTS, {})

        if self._devices is None:
            turkov_api = await async_get_updated_api(
                self.hass, self.config_entry
            )
            self._devices = {
                device.serial_number: device
                for device in turkov_api.devices.values()
                if device.serial_number
            }

        for serial in sorted({*hosts, *self._devices}):
            local_ip = hosts.get(serial, {}).get(CONF_HOST)
            name = f"S/N: {serial}"
            try:
                device = self._devices[serial]
            except KeyError:
                pass
            else:
                name = device.name or device.type or name
            if local_ip:
                name += f" ({local_ip})"
            menu_options[f"host_{serial}"] = name

        if not menu_options:
            self.async_abort("empty_hosts")

        return self.async_show_menu(step_id="hosts", menu_options=menu_options)

    async def async_step_host(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if is_local := (CONF_HOST in self.config_entry.data):
            current_host = self.config_entry.data
            schema = STEP_HOST_DATA_SCHEMA
        elif current_serial := self._current_serial:
            current_host = self.options.get(CONF_HOSTS, {}).get(current_serial)
            schema = STEP_HOST_OPTIONS_SCHEMA
        else:
            return self.async_abort(reason="unknown_error")

        errors = {}

        if user_input is None:
            user_input = current_host
        elif is_local:
            return self.async_create_entry(data=user_input)
        else:
            self.options.setdefault(CONF_HOSTS, {})[
                current_serial
            ] = user_input
            return await self.async_step_init()

        return self.async_show_form(
            step_id=STEP_HOST,
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input
            ),
            errors=errors,
        )

    def __getattr__(self, attribute):
        if isinstance(attribute, str) and attribute.startswith(
            f"async_step_{STEP_HOST}_"
        ):
            self._current_serial = attribute[16:]
            return self.async_step_host
        raise AttributeError
