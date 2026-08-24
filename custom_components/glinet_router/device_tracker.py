"""Client device trackers for GL.iNet Router."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, override

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GLiNetCoordinator
from .models import RouterClient

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up coordinator-backed client trackers."""
    coordinator: GLiNetCoordinator = entry.runtime_data.coordinator
    known_macs: set[str] = set()
    unique_id_prefix = f"{entry.unique_id or entry.entry_id}_client_"

    @callback
    def async_add_new_entities() -> None:
        if not coordinator.track_clients:
            return
        candidate_macs = {
            mac for mac, client in coordinator.data.clients.items() if client.connected
        }
        registry = er.async_get(hass)
        candidate_macs.update(
            entity.unique_id.removeprefix(unique_id_prefix)
            for entity in registry.entities.values()
            if entity.platform == DOMAIN
            and entity.domain == "device_tracker"
            and entity.config_entry_id == entry.entry_id
            and entity.unique_id.startswith(unique_id_prefix)
        )
        new_macs = candidate_macs - known_macs
        if not new_macs:
            return
        known_macs.update(new_macs)
        async_add_entities(
            GLiNetClientTracker(coordinator, entry, mac) for mac in sorted(new_macs)
        )

    async_add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(async_add_new_entities))


class GLiNetClientTracker(CoordinatorEntity[GLiNetCoordinator], ScannerEntity):
    """A router client using UniFi-style scanner semantics."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: GLiNetCoordinator,
        entry: ConfigEntry,
        mac: str,
    ) -> None:
        super().__init__(coordinator)
        self._mac = mac
        router_id = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{router_id}_client_{mac}"

    @property
    def _client(self) -> RouterClient | None:
        return self.coordinator.data.clients.get(self._mac)

    @property
    @override
    def available(self) -> bool:
        return super().available

    @property
    @override
    def entity_registry_enabled_default(self) -> bool:
        """Keep newly discovered GL.iNet clients enabled by default."""
        return True

    @property
    @override
    def name(self) -> str:
        client = self._client
        return client.name if client and client.name else self._mac

    @property
    @override
    def is_connected(self) -> bool:
        client = self._client
        return bool(client and client.connected)

    @property
    @override
    def mac_address(self) -> str:
        return self._mac

    @property
    @override
    def unique_id(self) -> str:
        """Return a router-scoped client identity instead of the bare MAC."""
        return self._attr_unique_id

    @property
    @override
    def ip_address(self) -> str | None:
        client = self._client
        return client.ip_address if client else None

    @property
    @override
    def hostname(self) -> str | None:
        client = self._client
        return client.name if client else None

    @property
    @override
    def extra_state_attributes(self) -> Mapping[str, Any]:
        client = self._client
        if client is None:
            return {}
        if client.remote:
            connection_type = "remote"
        elif client.interface == "cable":
            connection_type = "wired"
        elif client.interface in {"2.4G", "5G"}:
            connection_type = "wireless"
        else:
            connection_type = "unknown"
        return {
            "connection_type": connection_type,
            "interface": client.interface,
            "blocked": client.blocked,
            "remote": client.remote,
        }
