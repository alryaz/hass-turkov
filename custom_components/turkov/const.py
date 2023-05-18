"""The Turkov Integration"""
from typing import Final, Tuple, FrozenSet

DOMAIN = "turkov"
CONF_ACCESS_TOKEN_EXPIRES_AT: Final[str] = "access_token_expires_at"
CONF_REFRESH_TOKEN: Final[str] = "refresh_token"
CONF_REFRESH_TOKEN_EXPIRES_AT: Final[str] = "refresh_token_expires_at"

CLIMATE_ATTR_TARGET_TEMPERATURE: Final[str] = "target_temperature"
CLIMATE_ATTR_CURRENT_TEMPERATURE: Final[str] = "indoor_temperature"
CLIMATE_ATTR_HVAC_IS_ON: Final[str] = "is_on"

CLIMATE_ATTRS: Final[FrozenSet[str]] = frozenset(
    (
        CLIMATE_ATTR_TARGET_TEMPERATURE,
        CLIMATE_ATTR_CURRENT_TEMPERATURE,
        CLIMATE_ATTR_HVAC_IS_ON,
    )
)
