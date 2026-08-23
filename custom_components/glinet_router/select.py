"""Select platform for GL.iNet Router controls."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GLiNetCoordinator
from .entity import GLiNetEntity
from .models import PRIORITY_OPTIONS

INTERNET_PRIORITY = SelectEntityDescription(
    key="internet_priority",
    name="Internet priority",
    icon="mdi:format-list-numbered",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up GL.iNet select entities."""
    coordinator: GLiNetCoordinator = entry.runtime_data.coordinator
    if "multiwan" in coordinator.data.capabilities:
        async_add_entities([GLiNetInternetPrioritySelect(coordinator, entry)])


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
