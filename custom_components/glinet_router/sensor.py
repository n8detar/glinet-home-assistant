"""Sensor platform for the GL.iNet Router integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    SIGNAL_STRENGTH_DECIBELS,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GLiNetCoordinator
from .entity import GLiNetEntity


@dataclass(frozen=True, kw_only=True)
class GLiNetSensorDescription(SensorEntityDescription):
    """Describe a GL.iNet sensor."""

    value_fn: Callable[[dict[str, Any]], Any] = lambda values: None


def _value(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda values: values.get(key)


SENSORS: tuple[GLiNetSensorDescription, ...] = (
    GLiNetSensorDescription(
        key="uptime",
        name="Uptime",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_value("uptime"),
    ),
    GLiNetSensorDescription(
        key="cpu_temperature",
        name="CPU temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_value("cpu_temperature"),
    ),
    *tuple(
        GLiNetSensorDescription(
            key=key,
            name=name,
            icon="mdi:chart-bell-curve-cumulative",
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=_value(key),
        )
        for key, name in (
            ("load_1m", "Load 1 minute"),
            ("load_5m", "Load 5 minutes"),
            ("load_15m", "Load 15 minutes"),
        )
    ),
    GLiNetSensorDescription(
        key="memory_usage",
        name="Memory usage",
        icon="mdi:memory",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_value("memory_usage"),
    ),
    GLiNetSensorDescription(
        key="flash_usage",
        name="Flash usage",
        icon="mdi:harddisk",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_value("flash_usage"),
    ),
    *tuple(
        GLiNetSensorDescription(
            key=key,
            name=name,
            icon="mdi:memory" if key.startswith("memory") else "mdi:harddisk",
            device_class=SensorDeviceClass.DATA_SIZE,
            native_unit_of_measurement=UnitOfInformation.BYTES,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=_value(key),
        )
        for key, name in (
            ("memory_free", "Memory free"),
            ("memory_total", "Memory total"),
            ("flash_free", "Flash free"),
            ("flash_total", "Flash total"),
        )
    ),
    GLiNetSensorDescription(
        key="fan_rpm",
        name="Fan speed",
        icon="mdi:fan",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_value("fan_rpm"),
    ),
    *tuple(
        GLiNetSensorDescription(
            key=key,
            name=name,
            icon=icon,
            value_fn=_value(key),
        )
        for key, name, icon in (
            ("active_wan", "Active internet connection", "mdi:wan"),
            ("multiwan_mode", "Multi-WAN mode", "mdi:call-split"),
            ("multiwan_sensitivity", "Multi-WAN sensitivity", "mdi:gauge"),
            ("active_sim", "Active SIM slot", "mdi:sim"),
            ("cellular_carrier", "Cellular carrier", "mdi:access-point-network"),
            ("cellular_network_type", "Cellular network type", "mdi:signal-5g"),
            ("cellular_bands", "Cellular bands", "mdi:radio-tower"),
            (
                "cellular_downlink_bandwidth",
                "Cellular downlink bandwidth",
                "mdi:download-network",
            ),
        )
    ),
    *tuple(
        GLiNetSensorDescription(
            key=key,
            name=name,
            icon="mdi:signal",
            native_unit_of_measurement=unit,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=_value(key),
        )
        for key, name, unit in (
            ("cellular_rsrp", "Cellular RSRP", SIGNAL_STRENGTH_DECIBELS_MILLIWATT),
            ("cellular_rsrq", "Cellular RSRQ", SIGNAL_STRENGTH_DECIBELS),
            ("cellular_sinr", "Cellular SINR", SIGNAL_STRENGTH_DECIBELS),
            ("cellular_rssi", "Cellular RSSI", SIGNAL_STRENGTH_DECIBELS_MILLIWATT),
        )
    ),
    GLiNetSensorDescription(
        key="cellular_traffic_total",
        name="Cellular traffic total",
        icon="mdi:counter",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_value("cellular_traffic_total"),
    ),
    GLiNetSensorDescription(
        key="unread_sms",
        name="Unread SMS",
        icon="mdi:message-badge",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_value("unread_sms"),
    ),
    *tuple(
        GLiNetSensorDescription(
            key=key,
            name=name,
            icon=icon,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=_value(key),
        )
        for key, name, icon in (
            ("online_clients", "Online clients", "mdi:devices"),
            ("wireless_clients", "Wireless clients", "mdi:wifi"),
            ("wired_clients", "Wired clients", "mdi:ethernet"),
            ("wifi_radios_enabled", "Wi-Fi radios enabled", "mdi:wifi-cog"),
            ("vpn_tunnels", "VPN tunnels", "mdi:vpn"),
            ("firewall_rules", "Firewall rules", "mdi:shield-check"),
            ("port_forwards", "Port forwards", "mdi:lan-connect"),
        )
    ),
    *tuple(
        GLiNetSensorDescription(
            key=key,
            name=name,
            icon="mdi:code-braces",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_fn=_value(key),
        )
        for key, name in (
            ("router_mode", "Router mode code"),
            ("tailscale_status_code", "Tailscale status code"),
            ("ddns_status_code", "DDNS status code"),
            ("zerotier_status_code", "ZeroTier status code"),
        )
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up GL.iNet sensors."""
    coordinator: GLiNetCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        GLiNetSensor(coordinator, entry, description)
        for description in SENSORS
        if description.key in coordinator.data.values
    )


class GLiNetSensor(GLiNetEntity, SensorEntity):
    """A privacy-safe GL.iNet sensor."""

    entity_description: GLiNetSensorDescription

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data.values)
