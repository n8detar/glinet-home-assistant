"""Base entity for the GL.iNet Router integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import GLiNetCoordinator


class GLiNetEntity(CoordinatorEntity[GLiNetCoordinator]):
    """Base coordinator-backed GL.iNet entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GLiNetCoordinator,
        entry: ConfigEntry,
        description: EntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        router_id = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{router_id}_{description.key}"
        snapshot = coordinator.data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, router_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=snapshot.device.get("model", "GL.iNet Router"),
            sw_version=snapshot.device.get("firmware"),
            hw_version=snapshot.device.get("modem"),
            configuration_url=coordinator.client.endpoint.rsplit("/rpc", 1)[0],
        )
