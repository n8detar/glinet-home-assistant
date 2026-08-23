"""Binary sensor platform for the GL.iNet Router integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GLiNetCoordinator
from .entity import GLiNetEntity


@dataclass(frozen=True, kw_only=True)
class GLiNetBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a GL.iNet binary sensor."""

    data_key: str


BINARY_SENSORS: tuple[GLiNetBinarySensorDescription, ...] = (
    GLiNetBinarySensorDescription(
        key="internet_connected",
        data_key="internet_connected",
        name="Internet",
        icon="mdi:web",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    GLiNetBinarySensorDescription(
        key="cellular_connected",
        data_key="cellular_connected",
        name="Cellular",
        icon="mdi:signal-5g",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    *tuple(
        GLiNetBinarySensorDescription(
            key=key,
            data_key=key,
            name=name,
            icon=icon,
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
        )
        for key, name, icon in (
            ("repeater_healthy", "Repeater health", "mdi:wifi-sync"),
            ("ethernet_1_healthy", "Ethernet 1 health", "mdi:ethernet"),
            ("cellular_healthy", "Cellular health", "mdi:signal-5g"),
            ("tethering_healthy", "Tethering health", "mdi:usb"),
            ("ethernet_2_healthy", "Ethernet 2 health", "mdi:ethernet"),
        )
    ),
    GLiNetBinarySensorDescription(
        key="tailscale_connected",
        data_key="tailscale_connected",
        name="Tailscale connected",
        icon="mdi:vpn",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    GLiNetBinarySensorDescription(
        key="vpn_client_enabled",
        data_key="vpn_client_enabled",
        name="VPN client enabled",
        icon="mdi:vpn",
    ),
    GLiNetBinarySensorDescription(
        key="adguard_running",
        data_key="adguard_running",
        name="AdGuard Home running",
        icon="mdi:shield-check",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    GLiNetBinarySensorDescription(
        key="time_synchronized",
        data_key="time_synchronized",
        name="Time synchronized",
        icon="mdi:clock-check",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    GLiNetBinarySensorDescription(
        key="fan_running",
        data_key="fan_running",
        name="Fan running",
        icon="mdi:fan",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    *tuple(
        GLiNetBinarySensorDescription(
            key=key,
            data_key=key,
            name=name,
            icon=icon,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        for key, name, icon in (
            ("wifi_2g_enabled", "2.4 GHz Wi-Fi enabled", "mdi:wifi"),
            ("wifi_5g_enabled", "5 GHz Wi-Fi enabled", "mdi:wifi"),
            ("ddns_enabled", "DDNS enabled", "mdi:dns"),
            ("zerotier_enabled", "ZeroTier enabled", "mdi:vpn"),
            ("service_wgserver_running", "WireGuard server running", "mdi:vpn"),
            ("service_ovpnserver_running", "OpenVPN server running", "mdi:vpn"),
            ("service_tor_running", "Tor running", "mdi:incognito"),
        )
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up GL.iNet binary sensors."""
    coordinator: GLiNetCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        GLiNetBinarySensor(coordinator, entry, description)
        for description in BINARY_SENSORS
        if description.data_key in coordinator.data.binary
    )


class GLiNetBinarySensor(GLiNetEntity, BinarySensorEntity):
    """A privacy-safe GL.iNet binary sensor."""

    entity_description: GLiNetBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.binary.get(self.entity_description.data_key)
