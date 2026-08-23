"""DataUpdateCoordinator for the GL.iNet Router integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GLiNetApiClient, GLiNetAuthenticationError, GLiNetError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .models import RouterSnapshot

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
            return await self.client.async_get_snapshot()
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
