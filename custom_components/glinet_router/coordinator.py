"""DataUpdateCoordinator for the GL.iNet Router integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from time import monotonic

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GLiNetApiClient, GLiNetAuthenticationError, GLiNetError
from .const import (
    CONF_DETECTION_TIME,
    CONF_IGNORE_LOCAL_MAC,
    CONF_SCAN_INTERVAL,
    CONF_TRACK_CLIENTS,
    CONF_TRACK_WIRED_CLIENTS,
    DEFAULT_DETECTION_TIME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_SMS_RECEIVED,
)
from .models import ClientPresenceStore, RouterSnapshot, SmsInboxTracker

_LOGGER = logging.getLogger(__name__)


class GLiNetCoordinator(DataUpdateCoordinator[RouterSnapshot]):
    """Coordinate polling and serialized control refreshes."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: GLiNetApiClient,
    ) -> None:
        self.entry = entry
        self.client = client
        self.track_clients = bool(entry.options.get(CONF_TRACK_CLIENTS, True))
        self._client_presence = ClientPresenceStore(
            detection_time=int(
                entry.options.get(CONF_DETECTION_TIME, DEFAULT_DETECTION_TIME)
            ),
            include_wired=bool(entry.options.get(CONF_TRACK_WIRED_CLIENTS, True)),
            ignore_local_mac=bool(entry.options.get(CONF_IGNORE_LOCAL_MAC, False)),
        )
        self._sms_inbox = SmsInboxTracker()
        self._sms_inbox_supported = False
        scan_interval = int(
            entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> RouterSnapshot:
        try:
            snapshot = await self.client.async_get_snapshot(
                include_clients=self.track_clients
            )
            if self.track_clients:
                snapshot.clients = self._client_presence.update(
                    snapshot.clients, now=monotonic()
                )
            if "sms" in snapshot.capabilities:
                try:
                    messages = await self.client.async_get_sms_messages()
                except GLiNetAuthenticationError:
                    raise
                except (GLiNetError, ClientError, TimeoutError):
                    pass
                else:
                    self._sms_inbox_supported = True
                    for message in self._sms_inbox.process(messages):
                        self.hass.bus.async_fire(
                            EVENT_SMS_RECEIVED,
                            {
                                "config_entry_id": self.entry.entry_id,
                                "message_id": message.message_id,
                                "from": message.sender,
                                "message": message.message,
                                "date": message.date,
                            },
                        )
            if self._sms_inbox_supported:
                snapshot.capabilities.add("sms_inbox")
            return snapshot
        except GLiNetAuthenticationError as err:
            raise ConfigEntryAuthFailed("GL.iNet authentication failed") from err
        except (GLiNetError, ClientError, TimeoutError) as err:
            raise UpdateFailed("Unable to update GL.iNet router") from err

    async def async_set_internet_priority(self, option: str) -> None:
        await self.client.async_set_internet_priority(option)
        await self.async_request_refresh()

    async def async_set_tailscale(self, key: str, enabled: bool) -> None:
        await self.client.async_set_tailscale(key, enabled)
        await self.async_request_refresh()

    async def async_set_adguard(self, key: str, enabled: bool) -> None:
        await self.client.async_set_adguard(key, enabled)
        await self.async_request_refresh()

    async def async_reboot_router(self) -> None:
        """Request a router reboot without immediately polling the rebooting device."""
        await self.client.async_reboot_router()

    async def async_reconnect_cellular(self) -> None:
        """Reconnect the discovered cellular modem and refresh state."""
        bus = self.data.values.get("modem_bus")
        if not isinstance(bus, str):
            raise GLiNetError("No cellular modem bus is available")
        await self.client.async_reconnect_cellular(bus=bus)
        await self.async_request_refresh()

    async def async_mark_all_sms_read(self) -> None:
        """Mark every unread inbound SMS read, then refresh state."""
        await self.client.async_mark_all_sms_read()
        await self.async_request_refresh()

    async def async_delete_all_read_sms(self) -> None:
        """Delete every SMS currently marked read, then refresh state."""
        await self.client.async_delete_all_read_sms()
        await self.async_request_refresh()
