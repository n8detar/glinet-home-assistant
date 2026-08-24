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
    discovery_capability: str | None = None


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
    GLiNetButtonDescription(
        key="mark_all_sms_read",
        name="Mark all SMS read",
        action="mark_all_sms_read",
        required_capability="sms_inbox",
        discovery_capability="sms",
        icon="mdi:email-check-outline",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    GLiNetButtonDescription(
        key="delete_all_read_sms",
        name="Delete all read SMS",
        action="delete_all_read_sms",
        required_capability="sms_inbox",
        discovery_capability="sms",
        icon="mdi:delete-sweep-outline",
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
        if (description.discovery_capability or description.required_capability)
        in coordinator.data.capabilities
    )


class GLiNetButton(GLiNetEntity, ButtonEntity):
    """An explicitly enabled disruptive router action."""

    entity_description: GLiNetButtonDescription

    @property
    def available(self) -> bool:
        """Expose the button only while its mutation capability is verified."""
        return (
            super().available
            and self.entity_description.required_capability
            in self.coordinator.data.capabilities
        )

    async def async_press(self) -> None:
        """Execute the selected disruptive action."""
        try:
            if self.entity_description.action == "reboot_router":
                await self.coordinator.async_reboot_router()
            elif self.entity_description.action == "reconnect_cellular":
                await self.coordinator.async_reconnect_cellular()
            elif self.entity_description.action == "mark_all_sms_read":
                await self.coordinator.async_mark_all_sms_read()
            elif self.entity_description.action == "delete_all_read_sms":
                await self.coordinator.async_delete_all_read_sms()
            else:
                raise HomeAssistantError("Unsupported GL.iNet button action")
        except GLiNetError as err:
            raise HomeAssistantError(
                f"GL.iNet {self.entity_description.name} action failed"
            ) from err
