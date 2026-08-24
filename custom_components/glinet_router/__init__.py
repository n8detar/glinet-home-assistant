"""GL.iNet Router integration setup."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GLiNetApiClient
from .const import (
    ATTR_MESSAGE,
    ATTR_PHONE_NUMBER,
    CONF_USE_SSL,
    DOMAIN,
    SERVICE_SEND_SMS,
)
from .coordinator import GLiNetCoordinator
from .util import build_endpoint

PLATFORMS: tuple[Platform, ...] = (
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.BUTTON,
)

ATTR_CONFIG_ENTRY_ID = "config_entry_id"

SEND_SMS_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_PHONE_NUMBER): vol.All(cv.string, vol.Length(min=3, max=32)),
        vol.Required(ATTR_MESSAGE): vol.All(cv.string, vol.Length(min=1, max=1600)),
    }
)


@dataclass(slots=True)
class GLiNetRuntimeData:
    """Runtime objects belonging to one config entry."""

    client: GLiNetApiClient
    coordinator: GLiNetCoordinator


GLiNetConfigEntry = ConfigEntry[GLiNetRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: GLiNetConfigEntry) -> bool:
    """Set up a GL.iNet router from a config entry."""
    endpoint = build_endpoint(
        entry.data[CONF_HOST], use_ssl=entry.data.get(CONF_USE_SSL, False)
    )
    session = async_get_clientsession(
        hass, verify_ssl=entry.data.get(CONF_VERIFY_SSL, False)
    )
    client = GLiNetApiClient(
        endpoint=endpoint,
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        session=session,
    )
    coordinator = GLiNetCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = GLiNetRuntimeData(client=client, coordinator=coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    loaded_entries: set[str] = hass.data.setdefault(DOMAIN, set())
    loaded_entries.add(entry.entry_id)
    if not hass.services.has_service(DOMAIN, SERVICE_SEND_SMS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_SMS,
            partial(_async_handle_send_sms, hass),
            schema=SEND_SMS_SCHEMA,
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GLiNetConfigEntry) -> bool:
    """Unload a GL.iNet router."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    loaded_entries: set[str] = hass.data.get(DOMAIN, set())
    loaded_entries.discard(entry.entry_id)
    if not loaded_entries and hass.services.has_service(DOMAIN, SERVICE_SEND_SMS):
        hass.services.async_remove(DOMAIN, SERVICE_SEND_SMS)
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: GLiNetConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_handle_send_sms(hass: HomeAssistant, call: ServiceCall) -> None:
    """Route an SMS action to one loaded router without logging its contents."""
    requested_entry = call.data.get(ATTR_CONFIG_ENTRY_ID)
    candidates = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id in hass.data.get(DOMAIN, set())
        and (requested_entry is None or entry.entry_id == requested_entry)
    ]
    if len(candidates) != 1:
        raise ServiceValidationError(
            "Select exactly one loaded GL.iNet router with config_entry_id"
        )
    entry: GLiNetConfigEntry = candidates[0]
    bus = entry.runtime_data.coordinator.data.values.get("modem_bus")
    if not isinstance(bus, str):
        raise ServiceValidationError("The selected router has no SMS-capable modem")
    await entry.runtime_data.client.async_send_sms(
        bus=bus,
        phone_number=call.data[ATTR_PHONE_NUMBER],
        message=call.data[ATTR_MESSAGE],
    )
