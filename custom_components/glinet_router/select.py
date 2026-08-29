"""Select platform for GL.iNet Router controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GLiNetCoordinator
from .entity import GLiNetEntity
from .models import PRIORITY_OPTIONS, WIFI_TX_POWER_OPTIONS

INTERNET_PRIORITY = SelectEntityDescription(
    key="internet_priority",
    name="Internet priority",
    icon="mdi:format-list-numbered",
)


@dataclass(frozen=True, kw_only=True)
class GLiNetWifiTxPowerDescription(SelectEntityDescription):
    """Describe a capability-gated Wi-Fi transmit-power control."""

    band: str
    capability: str
    data_key: str


WIFI_TX_POWER_SELECTS: tuple[GLiNetWifiTxPowerDescription, ...] = (
    GLiNetWifiTxPowerDescription(
        key="wifi_2g_tx_power",
        band="2g",
        capability="wifi_2g_tx_power",
        data_key="wifi_2g_tx_power",
        name="2.4 GHz Wi-Fi TX power",
        icon="mdi:signal",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    GLiNetWifiTxPowerDescription(
        key="wifi_5g_tx_power",
        band="5g",
        capability="wifi_5g_tx_power",
        data_key="wifi_5g_tx_power",
        name="5 GHz Wi-Fi TX power",
        icon="mdi:signal",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up GL.iNet select entities."""
    coordinator: GLiNetCoordinator = entry.runtime_data.coordinator
    entities: list[SelectEntity] = []
    if "multiwan" in coordinator.data.capabilities:
        entities.append(GLiNetInternetPrioritySelect(coordinator, entry))
    entities.extend(
        GLiNetWifiTxPowerSelect(coordinator, entry, description)
        for description in WIFI_TX_POWER_SELECTS
        if description.capability in coordinator.data.capabilities
    )
    async_add_entities(entities)


class GLiNetInternetPrioritySelect(GLiNetEntity, SelectEntity):
    """Switch Ethernet 1 and cellular between failover positions 2 and 3."""

    _attr_options: ClassVar[list[str]] = list(PRIORITY_OPTIONS)

    def __init__(self, coordinator: GLiNetCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, INTERNET_PRIORITY)

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.data.values.get("internet_priority")
        return value if isinstance(value, str) else None

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data.values.get("multiwan_mode") == "Failover"
        )

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_internet_priority(option)


class GLiNetWifiTxPowerSelect(GLiNetEntity, SelectEntity):
    """Constrained transmit-power selector for one Wi-Fi band."""

    _attr_options: ClassVar[list[str]] = list(WIFI_TX_POWER_OPTIONS)
    entity_description: GLiNetWifiTxPowerDescription

    def __init__(
        self,
        coordinator: GLiNetCoordinator,
        entry: ConfigEntry,
        description: GLiNetWifiTxPowerDescription,
    ) -> None:
        super().__init__(coordinator, entry, description)

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.data.values.get(self.entity_description.data_key)
        return value if value in WIFI_TX_POWER_OPTIONS else None

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.entity_description.data_key in self.coordinator.data.values
        )

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_wifi_tx_power(
            self.entity_description.band, option
        )
