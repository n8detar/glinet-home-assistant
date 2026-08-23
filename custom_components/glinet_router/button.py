"""Button platform for explicitly enabled disruptive GL.iNet controls."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import GLiNetError
from .coordinator import GLiNetCoordinator
from .entity import GLiNetEntity


@dataclass(frozen=True, kw_only=True)
class GLiNetButtonDescription(ButtonEntityDescription):
    """Describe a disruptive, capability-gated router action."""

    action: str
    required_capability: str


BUTTONS: tuple[GLiNetButtonDescription, ...] = (
    GLiNetButtonDescription(
        key="reboot_router",
        name="Reboot router",
        action="reboot_router",
        required_capability="router",
        icon="mdi:restart",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    GLiNetButtonDescription(
        key="reconnect_cellular",
        name="Reconnect cellular",
        action="reconnect_cellular",
        required_capability="modem",
        icon="mdi:signal-5g",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up supported GL.iNet buttons as disabled-by-default entities."""
    coordinator: GLiNetCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        GLiNetButton(coordinator, entry, description)
        for description in BUTTONS
        if description.required_capability in coordinator.data.capabilities
    )


class GLiNetButton(GLiNetEntity, ButtonEntity):
    """An explicitly enabled disruptive router action."""

    entity_description: GLiNetButtonDescription

    async def async_press(self) -> None:
        """Execute the selected disruptive action."""
        try:
            if self.entity_description.action == "reboot_router":
                await self.coordinator.async_reboot_router()
            elif self.entity_description.action == "reconnect_cellular":
                await self.coordinator.async_reconnect_cellular()
            else:
                raise HomeAssistantError("Unsupported GL.iNet button action")
        except GLiNetError as err:
            raise HomeAssistantError(
                f"GL.iNet {self.entity_description.name} action failed"
            ) from err
