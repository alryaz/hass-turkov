import logging
from typing import (
    Final,
    Mapping,
    Any,
    TYPE_CHECKING,
    Iterable,
    Type,
)

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_VERIFY_SSL,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_ACCESS_TOKEN,
    CONF_HOST,
    CONF_HOSTS,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import TurkovAPI
from .const import (
    CONF_ENABLE_ALL_ENTITIES,
    CONF_ACCESS_TOKEN_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_REFRESH_TOKEN_EXPIRES_AT,
    DOMAIN,
)

if TYPE_CHECKING:
    from .entity import (
        TurkovDeviceUpdateCoordinator,
        TurkovEntityDescription,
        TurkovEntity,
    )

HOST_OPTIONS_SCHEMA: Final = vol.Schema(
    {
        vol.Optional(CONF_ENABLE_ALL_ENTITIES, default=False): cv.boolean,
    },
)
"""Schema for local entry options setup"""

STEP_HOST_LOCAL_OPTIONS_SCHEMA: Final = HOST_OPTIONS_SCHEMA
"""Schema for OptionsFlow -> host step (for local config)"""

STEP_CLOUD_HOST_OPTIONS_SCHEMA: Final = STEP_HOST_LOCAL_OPTIONS_SCHEMA.extend(
    {
        vol.Optional(CONF_HOST): cv.string,
    }
)
"""Schema for OptionsFlow -> host step (for cloud config)"""

STEP_CLOUD_OPTIONS_SCHEMA: Final = vol.Schema(
    {
        vol.Optional(CONF_VERIFY_SSL, default=True): cv.boolean,
    }
)
"""Schema for OptionsFlow -> cloud step"""

CLOUD_OPTIONS_SCHEMA: Final = STEP_CLOUD_OPTIONS_SCHEMA.extend(
    {
        vol.Optional(CONF_HOSTS, default=dict): {
            cv.string: HOST_OPTIONS_SCHEMA
        },
    }
)
"""Schema for cloud entry options setup"""

CLOUD_DATA_SCHEMA: Final = vol.Schema(
    {
        vol.Required(CONF_EMAIL): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)
"""Schema for cloud entry data setup"""

STEP_CLOUD_DATA_SCHEMA: Final = CLOUD_DATA_SCHEMA.extend(
    STEP_CLOUD_OPTIONS_SCHEMA.schema
)
"""Schema for ConfigFlow -> email step"""

HOST_DATA_SCHEMA: Final = HOST_OPTIONS_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)
"""Schema for ConfigFlow -> host step"""


async def async_get_updated_api(
    hass: HomeAssistant, entry: ConfigEntry | Mapping[str, Any]
) -> TurkovAPI:
    if isinstance(entry, ConfigEntry):
        options = entry.options
        entry = entry.data
    else:
        options = entry

    turkov_api = TurkovAPI(
        async_get_clientsession(hass, options[CONF_VERIFY_SSL]),
        entry[CONF_EMAIL],
        entry[CONF_PASSWORD],
        access_token=entry.get(CONF_ACCESS_TOKEN),
        access_token_expires_at=entry.get(CONF_ACCESS_TOKEN_EXPIRES_AT),
        refresh_token=entry.get(CONF_REFRESH_TOKEN),
        refresh_token_expires_at=entry.get(CONF_REFRESH_TOKEN_EXPIRES_AT),
    )

    await turkov_api.update_user_data(True)

    return turkov_api


async def async_setup_entry_for_platform(
    logger: logging.Logger,
    entity_types: Iterable["TurkovEntityDescription"],
    entity_class: Type["TurkovEntity"],
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Turkov <entity platform>."""
    turkov_update_coordinators: dict[
        str, "TurkovDeviceUpdateCoordinator"
    ] = hass.data[DOMAIN][entry.entry_id]

    add_entities = []
    for (
        identifier,
        coordinator,
    ) in turkov_update_coordinators.items():
        add_all_entities = coordinator.host_config[CONF_ENABLE_ALL_ENTITIES]

        device = coordinator.turkov_device
        for description in entity_types:
            add_entity = (
                getattr(device, description.value_source, None) is not None
            )
            if not (add_entity or add_all_entities):
                continue
            add_entities.append(
                entity_class(
                    turkov_device_coordinator=coordinator,
                    turkov_device_identifier=identifier,
                    entity_description=description,
                    enabled_default=add_entity,
                )
            )

    from homeassistant.helpers.entity_platform import (
        async_get_current_platform,
    )

    domain = async_get_current_platform().domain

    if add_entities:
        logger.debug(f"Adding {len(add_entities)} {domain} entities")
        async_add_entities(add_entities, update_before_add=False)
    else:
        logger.debug(f"Not adding any {domain} entities")
