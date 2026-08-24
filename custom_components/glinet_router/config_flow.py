"""Config flow for the GL.iNet Router integration."""

from __future__ import annotations

from typing import Any, override

import voluptuous as vol
from aiohttp import ClientError
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GLiNetApiClient, GLiNetAuthenticationError, GLiNetError
from .const import (
    CONF_DETECTION_TIME,
    CONF_IGNORE_LOCAL_MAC,
    CONF_SCAN_INTERVAL,
    CONF_TRACK_CLIENTS,
    CONF_TRACK_WIRED_CLIENTS,
    CONF_USE_SSL,
    DEFAULT_DETECTION_TIME,
    DEFAULT_HOST,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
    MIN_DETECTION_TIME,
    MIN_SCAN_INTERVAL,
)
from .util import build_endpoint, router_unique_id

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_USE_SSL, default=False): bool,
        vol.Required(CONF_VERIFY_SSL, default=False): bool,
    }
)


async def async_validate_input(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, str]:
    """Validate credentials without logging or retaining a session ID."""
    endpoint = build_endpoint(data[CONF_HOST], use_ssl=data[CONF_USE_SSL])
    session = async_get_clientsession(hass, verify_ssl=data[CONF_VERIFY_SSL])
    client = GLiNetApiClient(
        endpoint=endpoint,
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        session=session,
    )
    info = await client.async_get_system_info()
    title = str(info.get("hostname") or info.get("model") or "GL.iNet Router")
    if not title.lower().startswith("gl"):
        title = f"GL.iNet {title.upper()}"
    return {
        "title": title,
        "unique_id": router_unique_id(info, data[CONF_HOST]),
    }


class GLiNetConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle GL.iNet Router configuration."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> GLiNetOptionsFlow:
        return GLiNetOptionsFlow()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await async_validate_input(self.hass, user_input)
            except GLiNetAuthenticationError:
                errors["base"] = "invalid_auth"
            except (GLiNetError, ClientError, TimeoutError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )


class GLiNetOptionsFlow(OptionsFlow):
    """Handle polling options."""

    @override
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(cv.positive_int, vol.Range(min=MIN_SCAN_INTERVAL, max=3600)),
                vol.Required(
                    CONF_TRACK_CLIENTS,
                    default=self.config_entry.options.get(CONF_TRACK_CLIENTS, True),
                ): cv.boolean,
                vol.Required(
                    CONF_TRACK_WIRED_CLIENTS,
                    default=self.config_entry.options.get(
                        CONF_TRACK_WIRED_CLIENTS, True
                    ),
                ): cv.boolean,
                vol.Required(
                    CONF_IGNORE_LOCAL_MAC,
                    default=self.config_entry.options.get(CONF_IGNORE_LOCAL_MAC, False),
                ): cv.boolean,
                vol.Required(
                    CONF_DETECTION_TIME,
                    default=self.config_entry.options.get(
                        CONF_DETECTION_TIME, DEFAULT_DETECTION_TIME
                    ),
                ): vol.All(
                    cv.positive_int, vol.Range(min=MIN_DETECTION_TIME, max=3600)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
