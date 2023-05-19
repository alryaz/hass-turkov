import asyncio
import logging
from json import JSONDecodeError, loads
from types import MappingProxyType
from typing import (
    Optional,
    TypedDict,
    ClassVar,
    Dict,
    List,
    Mapping,
    MutableMapping,
    Union,
    Set,
    Tuple,
    Callable,
    Any,
    final, SupportsInt,
)

import aiohttp
from aiohttp import ContentTypeError
from aiohttp.hdrs import METH_GET, IF_NONE_MATCH, METH_POST
from aiohttp.typedefs import LooseHeaders
from homeassistant.util.dt import utcnow, utc_to_timestamp
from multidict import CIMultiDict

_LOGGER = logging.getLogger(__name__)


class DeviceDataResponseDict(TypedDict):
    _id: str
    serialNumber: Optional[str]
    pin: Optional[str]
    deviceType: Optional[str]
    deviceName: Optional[str]
    firmVer: Optional[str]
    image: Optional[str]


class UserDataResponseDict(TypedDict):
    devices: List[DeviceDataResponseDict]
    pushTokens: List[str]
    userEmail: str
    firstName: str
    lastName: str
    fathersName: str


class ErrorResponseDict(TypedDict):
    message: str


class SignInResponseDict(TypedDict):
    accessToken: str
    accessTokenExpiresAt: int
    refreshToken: str
    refreshTokenExpiresAt: int


class TurkovAPIError(Exception):
    """Base class for Turkov API errors"""


class TurkovAPIAuthenticationError(TurkovAPIError):
    """Authentication-related exceptions"""


class TurkovAPIValueError(TurkovAPIError, ValueError):
    """Data-related errors"""


def _log_hide_id(id_: str):
    return "*" + str(id_)[-4:]


class TurkovAPI:
    BASE_URL: ClassVar[str] = "https://turkovwifi.ru"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}[{'**'.join(v[0] for v in self._user_email.partition('@')) + '**'}]"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}[user_email={self._user_email}, devices={self._devices}]>"

    def __init__(
        self,
        session: aiohttp.ClientSession,
        user_email: str,
        password: str,
        handle_authentication: bool = True,
        *,
        access_token: Optional[str] = None,
        access_token_expires_at: Optional[int] = None,
        refresh_token: Optional[str] = None,
        refresh_token_expires_at: Optional[int] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        middle_name: Optional[str] = None,
    ) -> None:
        # Internals
        self._session = session
        self._devices: Dict[str, TurkovDevice] = {}
        self._request_history: Dict[str, str] = {}
        self.handle_authentication = handle_authentication

        # Required authentication data
        self._user_email = user_email
        self._password = password

        # Optional authentication data
        self._access_token = access_token
        self._access_token_expires_at = access_token_expires_at
        self._refresh_token = refresh_token
        self._refresh_token_expires_at = refresh_token_expires_at
        self.first_name = first_name
        self.last_name = last_name
        self.middle_name = middle_name

    @property
    def devices(self) -> Mapping[str, "TurkovDevice"]:
        return MappingProxyType(self._devices)

    @property
    def user_email(self) -> str:
        return self._user_email

    @property
    def password(self) -> str:
        return self._password

    @property
    def access_token(self) -> Optional[str]:
        return self._access_token

    @property
    def access_token_expires_at(self) -> Optional[int]:
        return self._access_token_expires_at

    @property
    def access_token_needs_update(self) -> bool:
        if not self._access_token:
            return True
        access_token_expires_at = self._access_token_expires_at
        if access_token_expires_at is None:
            return True
        return access_token_expires_at < utc_to_timestamp(utcnow())

    @property
    def refresh_token(self) -> Optional[str]:
        return self._refresh_token

    @property
    def refresh_token_expires_at(self) -> Optional[int]:
        return self._refresh_token_expires_at

    @property
    def refresh_token_needs_update(self) -> bool:
        if not self._refresh_token:
            return True
        refresh_token_expires_at = self._refresh_token_expires_at
        if refresh_token_expires_at is None:
            return True
        return refresh_token_expires_at < utc_to_timestamp(utcnow())

    @property
    def session(self) -> aiohttp.ClientSession:
        return self._session

    @session.setter
    def session(self, value: aiohttp.ClientSession) -> None:
        if not isinstance(value, aiohttp.ClientSession):
            raise ValueError("only a session can be set")
        self._session = value

    async def authenticate_with_email(
        self,
        user_email: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        """@TODO"""
        if not user_email:
            user_email = self._user_email
        if not password:
            password = self._password

        _LOGGER.info(f"[{self}] Preparing to authenticate with email/password combo")
        async with self._session.post(
            self.BASE_URL + "/user/signin",
            json={
                "userEmail": user_email,
                "password": password,
            },
        ) as response:
            try:
                data: Union[
                    SignInResponseDict, ErrorResponseDict
                ] = await response.json()

                _LOGGER.debug(f"[{self}] Authentication response data: {data}")

                # Pin current timestamp
                current_timestamp = utc_to_timestamp(utcnow())

                # Extract tokens and expiry information
                access_token = data["accessToken"]
                access_token_expires_at = int(data["accessTokenExpiresAt"])
                refresh_token = data["refreshToken"]
                refresh_token_expires_at = int(data["refreshTokenExpiresAt"])

            except (ContentTypeError, JSONDecodeError) as exp:
                raise TurkovAPIAuthenticationError(
                    f"Server returned invalid response"
                ) from exp

            except KeyError as exp:
                raise TurkovAPIAuthenticationError(
                    f"Server did not provide auth data {exp}: {data.get('message') or '<no message>'}"
                ) from exp

            except (ValueError, TypeError) as exp:
                raise TurkovAPIAuthenticationError(f"Server provided bad data: {exp}")

            # Some data validation
            if not (access_token or refresh_token):
                raise TurkovAPIAuthenticationError(f"Server provided empty auth data")
            if access_token_expires_at < current_timestamp:
                raise TurkovAPIAuthenticationError(
                    f"Server provided expired access token"
                )
            if refresh_token_expires_at < current_timestamp:
                raise TurkovAPIAuthenticationError(
                    f"Server provided expired refresh token"
                )

            _LOGGER.info(f"[{self}] Successful authentication, updating data")

            # Update auth data
            self._access_token = access_token
            self._refresh_token = refresh_token
            self._access_token_expires_at = access_token_expires_at
            self._refresh_token_expires_at = refresh_token_expires_at

    async def authenticate(self) -> None:
        if not self.refresh_token_needs_update:
            _LOGGER.debug(f"[{self}] Auth called, refresh not yet expired")
            try:
                await self.update_access_token()
                return
            except asyncio.CancelledError:
                raise
            except BaseException as exp:
                _LOGGER.debug(f"[{self}] Error: {exp}", exc_info=exp)
                _LOGGER.warning(
                    f"[{self}] Failed to refresh access token, using regular auth"
                )

        await self.authenticate_with_email()

    async def update_access_token(self, refresh_token: Optional[str] = None) -> None:
        raise NotImplementedError

    async def _handle_pre_auth(self):
        if self._session.closed:
            raise RuntimeError("Session is closed and must be renewed")
        if self.access_token_needs_update:
            if not self.handle_authentication:
                raise TurkovAPIAuthenticationError("Access token not yet retrieved")
            _LOGGER.debug(f"[{self}] Access token requires update before auth")
            await self.authenticate()
        else:
            _LOGGER.debug(f"[{self}] Authenticated request with valid token")

    async def prepare_authenticated_request(
        self,
        *args,
        headers: Optional[LooseHeaders] = None,
        request_tag: Optional[str] = None,
        **kwargs,
    ):
        await self._handle_pre_auth()

        if headers is None:
            headers = {}
        elif not isinstance(headers, MutableMapping):
            headers = CIMultiDict(headers)

        headers["x-access-token"] = self._access_token

        if request_tag is not None:
            try:
                if_none_match = self._request_history[request_tag]
            except KeyError:
                pass
            else:
                headers[IF_NONE_MATCH] = if_none_match

        return self._session.request(*args, headers=headers, **kwargs)

    async def update_user_data(self, force: bool = False) -> None:
        _LOGGER.debug(f"[{self}] Updating user information and list of devices")
        async with (
            await self.prepare_authenticated_request(
                METH_GET,
                self.BASE_URL + "/user",
                request_tag=(None if force else "user_data"),
            )
        ) as response:
            # # @TODO
            # if response.status == 304:
            #     _LOGGER.debug(f"[{self}] User data not modified, no updates")
            #     return

            try:
                user_data: UserDataResponseDict = await response.json()

                _LOGGER.debug(f"[{self}] User data response: {user_data}")

                device_datum = user_data["devices"]
                user_email = user_data["userEmail"]
                first_name = user_data["firstName"]
                last_name = user_data["lastName"]
                middle_name = user_data["fathersName"]

            except (KeyError, JSONDecodeError) as exp:
                raise TurkovAPIAuthenticationError(
                    f"Server did not provide user and/or device datum: {exp}"
                ) from exp

            self._user_email = user_email

            # Optional data
            self.first_name = first_name
            self.last_name = last_name
            self.middle_name = middle_name

            existing_devices = self._devices
            leftover_devices = set(existing_devices.keys())
            for device_data in device_datum:
                try:
                    id_ = device_data["_id"]
                except KeyError:
                    _LOGGER.warning(
                        f"[{self}] Device data does not contain ID: {device_data}"
                    )
                    continue
                if not id_:
                    _LOGGER.warning(
                        f"[{self}] Device data contains empty ID: {device_data}"
                    )
                    continue

                try:
                    device = existing_devices[id_]
                    _LOGGER.info(f"[{self}] Found existing device: {device}")
                except KeyError:
                    _LOGGER.info(
                        f"[{self}] Creating new device with ID: {_log_hide_id(id_)}"
                    )
                    device = TurkovDevice(self, id_)
                    existing_devices[id_] = device
                else:
                    leftover_devices.discard(id_)

                device.device_type = device_data["deviceType"]
                device.device_name = device_data["deviceName"]
                device.serial_number = device_data["serialNumber"]
                device.pin = device_data["pin"]
                device.firmware_version = device_data["firmVer"]

            # Discard leftover devices
            for id_ in leftover_devices:
                _LOGGER.info(
                    f"[{self}] Discarding obsolete device: {existing_devices[id_]}"
                )
                del existing_devices[id_]

            # # @TODO
            # self._request_history["user_data"] = ...


class TurkovDevice:
    @staticmethod
    def extract_image_url(image_id: Any):
        pass

    IMAGES_BY_DEVICE_TYPE: ClassVar[Mapping[str, str]] = {
        "Zenit": "/images/zenit.jpg",
        "Capsule": "/images/capsule.jpg",
        "i-Vent": "/images/ivent.jpg",
    }

    ATTRIBUTE_KEY_MAPPING: ClassVar[
        Mapping[str, Tuple[str, Optional[Callable[[Any], Any]]]]
    ] = {
        "is_on": ("on", None),
        "fan_speed": ("fan_speed", str),
        "fan_mode": ("fan_mode", None),
        "target_temperature": ("temp_sp", float),
        "selected_mode": ("mode", str),
        "configuration": ("setup", str),
        "filter_life_percentage": ("filter", float),
        "outdoor_temperature": ("out_temp", lambda x: float(x) / 10),
        "indoor_temperature": ("in_temp", lambda x: float(x) / 10),
        "image_url": ("image", False),
    }

    def __str__(self) -> str:
        return f"{self.__class__.__name__}[{_log_hide_id(self._id)}]"

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}"
            f"[id={self._id}, "
            f"{', '.join(k + '=' + str(getattr(self, k)) for k in self.ATTRIBUTE_KEY_MAPPING)}]>"
        )

    # noinspection PyShadowingBuiltins
    def __init__(
        self,
        api: TurkovAPI,
        id: str,
        *,
        serial_number: Optional[str] = None,
        pin: Optional[str] = None,
        device_type: Optional[str] = None,
        device_name: Optional[str] = None,
        firmware_version: Optional[str] = None,
        image_url: Optional[str] = None,
    ) -> None:
        if not api:
            raise ValueError("api cannot be empty")
        if not id:
            raise ValueError("id cannot be empty")

        # Required attributes
        self._api = api
        self._id = id

        # Optional attributes
        self.serial_number = serial_number
        self.pin = pin
        self.device_type = device_type
        self.device_name = device_name
        self.firmware_version = firmware_version
        self.image_url = image_url

        # Placeholders
        self.is_on: Optional[bool] = None
        self.fan_speed: Optional[str] = None
        self.fan_mode: Optional[str] = None
        self.target_temperature: Optional[float] = None
        # self.current_mode: Optional[str] = None
        self.selected_mode: Optional[str] = None
        self.filter_life_percentage: Optional[float] = None
        self.outdoor_temperature: Optional[float] = None
        self.indoor_temperature: Optional[float] = None
        self.configuration: Optional[str] = None

    @final
    @property
    def api(self) -> TurkovAPI:
        return self._api

    @final
    @property
    def id(self) -> str:
        return self._id

    async def update_state(self, mark_as_none_if_not_present: bool = False) -> Set[str]:
        api = self._api
        async with (
            await api.prepare_authenticated_request(
                METH_GET,
                api.BASE_URL + "/user/devices",
                params={"device": f"{self._id}_state"},
            )
        ) as response:
            try:
                device_data_list = await response.json()
            except (ContentTypeError, JSONDecodeError):
                raise TurkovAPIError(
                    f"[{self}] Error decoding json data: {await response.text()}"
                )

        _LOGGER.debug(f"[{self}] Device update data: {device_data_list}")

        changed_attributes = set()

        # @TODO: this is done for a single 'Capsule' device, review others
        if isinstance(device_data_list, List):
            try:
                device_data_text = device_data_list[-1]
            except IndexError:
                raise TurkovAPIError(f"[{self}] Missing device data")

            try:
                device_data = loads(device_data_text)
            except JSONDecodeError:
                raise TurkovAPIError(f"[{self}] Improper device data encoding")

            _LOGGER.debug(f"[{self}] Decoded device update data: {device_data}")

            def set_attribute(attr_: str, value_: Any):
                _LOGGER.debug(f"[{self}] Setting '{attr_}' = '{value_}'")
                setattr(self, attr_, value_)
                changed_attributes.add(attr_)

            # Generic attribute handling process
            for attribute_name, (
                key,
                converter,
            ) in self.ATTRIBUTE_KEY_MAPPING.items():
                if converter is False:
                    continue

                try:
                    value = device_data[key]
                except KeyError:
                    if not mark_as_none_if_not_present:
                        continue
                    value = None
                else:
                    if callable(converter):
                        value = converter(value)

                if value != getattr(self, attribute_name):
                    set_attribute(attribute_name, value)

            # Custom attribute handling process
            image_url = device_data.get("image") or None
            if image_url:
                # Custom image detected
                image_url = f"{self.api.BASE_URL}/upload/{self._id}_{image_url}.jpg"
            elif self.device_type in self.IMAGES_BY_DEVICE_TYPE:
                # Select image based on device type
                image_url = self.IMAGES_BY_DEVICE_TYPE[self.device_type]
                if image_url.startswith("/"):
                    image_url = self.api.BASE_URL + image_url

            if (
                (image_url is None and self.image_url is not None)
                if mark_as_none_if_not_present
                else (self.image_url != image_url)
            ):
                set_attribute("image_url", image_url)

        else:
            _LOGGER.warning(f"[{self}] No data received for this device. This is new.")
            for attribute_name in self.ATTRIBUTE_KEY_MAPPING.keys():
                value = getattr(self, attribute_name, None)
                if value is None:
                    continue
                if mark_as_none_if_not_present:
                    setattr(self, attribute_name, None)
                    changed_attributes.add(attribute_name)
                else:
                    _LOGGER.warning(
                        f"[{self}] Cowardly refusing to update device with absence of data"
                    )
                    break

        return changed_attributes

    async def set_values(self, **kwargs) -> None:
        printed_values = ', '.join(f'{k}={v}' for k, v in kwargs.items())
        _LOGGER.debug(f"[{self}] Willing to set values: {printed_values}")

        api = self._api
        async with (
            await api.prepare_authenticated_request(
                METH_POST,
                api.BASE_URL + f"/user/devices/{self._id}",
                json=kwargs,
            )
        ) as response:
            try:
                message = (await response.json())["message"]
            except (ContentTypeError, JSONDecodeError) as exc:
                raise TurkovAPIError(
                    f"[{self}] Error decoding json data: {await response.text()}"
                ) from exc
            except (KeyError, ValueError, IndexError, TypeError, AttributeError) as exc:
                raise TurkovAPIError(f"[{self}] Response contains no message") from exc

            if message != "success":
                raise TurkovAPIError(f"[{self}] Error calling setter: {message}")

            _LOGGER.debug(
                f"[{self}] Successfully set: {printed_values}"
            )

    async def set_value(self, key: str, value: Any) -> None:
        await self.set_values(**{key: value})

    async def toggle_heater(self, turn_on: Optional[bool] = None) -> None:
        if turn_on is None:
            turn_on = self.selected_mode == "none"

        await (self.turn_on_heater if turn_on else self.turn_off_heater)()

    @property
    def has_heater(self) -> bool:
        return self.configuration == "heating"

    @property
    def is_heater_on(self) -> bool:
        return self.selected_mode == "heating"

    async def turn_on_heater(self) -> None:
        await self.set_value("mode", "1")

    async def turn_off_heater(self) -> None:
        await self.set_value("mode", "0")

    async def toggle(self, turn_on: Optional[bool] = None) -> None:
        if turn_on is None:
            turn_on = self.is_on

        await (self.turn_on if turn_on else self.turn_off)()

    async def turn_on(self) -> None:
        await self.set_value("on", "true")

    async def turn_off(self) -> None:
        await self.set_value("on", "false")

    async def set_fan_speed(self, fan_speed: str) -> None:
        if fan_speed not in ("A", "0", "1", "2", "3"):
            raise TurkovAPIValueError("valid fan speed not specified")

        await self.set_value("fan_speed", fan_speed)

    async def set_target_temperature(self, target_temperature: Union[int, SupportsInt]) -> None:
        target_temperature = int(target_temperature)

        if not (15 <= target_temperature <= 50):
            raise TurkovAPIValueError("target temperature out of bounds")

        await self.set_value("temp_sp", target_temperature)
