"""Config flow for Turkov integration."""

import logging
from hashlib import md5
from typing import Any, Optional, Dict

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_VERIFY_SSL
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import TurkovAPI, TurkovAPIError
from .api import TurkovAPIAuthenticationError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_VERIFY_SSL, default=True): bool,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Turkov."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
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
            unique_id = md5(user_input[CONF_EMAIL].encode("utf-8")).hexdigest()

            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input[CONF_EMAIL],
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
