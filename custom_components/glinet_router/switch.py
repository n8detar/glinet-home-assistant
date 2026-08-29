"""Switch platform for GL.iNet Router controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GLiNetCoordinator
from .entity import GLiNetEntity


@dataclass(frozen=True, kw_only=True)
class GLiNetSwitchDescription(SwitchEntityDescription):
    """Describe a narrowly scoped router control."""

    control: str
    data_key: str
    setting: str | None = None


SWITCHES: tuple[GLiNetSwitchDescription, ...] = (
    GLiNetSwitchDescription(
        key="status_leds",
        data_key="led_enabled",
        control="led",
        name="Status LEDs",
        icon="mdi:led-on",
        entity_category=EntityCategory.CONFIG,
    ),
    GLiNetSwitchDescription(
        key="wifi_2g_enabled_control",
        data_key="wifi_2g_enabled",
        setting="2g",
        control="wifi_2g_control",
        name="2.4 GHz Wi-Fi",
        icon="mdi:wifi",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    GLiNetSwitchDescription(
        key="wifi_5g_enabled_control",
        data_key="wifi_5g_enabled",
        setting="5g",
        control="wifi_5g_control",
        name="5 GHz Wi-Fi",
        icon="mdi:wifi",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    GLiNetSwitchDescription(
        key="adguard_enabled_control",
        data_key="adguard_enabled",
        setting="enabled",
        control="adguard",
        name="AdGuard Home",
        icon="mdi:shield-check",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    GLiNetSwitchDescription(
        key="adguard_dns_control",
        data_key="adguard_dns_enabled",
        setting="dns_enabled",
        control="adguard",
        name="AdGuard Home DNS protection",
        icon="mdi:dns",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    GLiNetSwitchDescription(
        key="tailscale_enabled_control",
        data_key="tailscale_enabled",
        setting="enabled",
        control="tailscale",
        name="Tailscale",
        icon="mdi:vpn",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    GLiNetSwitchDescription(
        key="tailscale_lan_access_control",
        data_key="tailscale_lan_access",
        setting="lan_enabled",
        control="tailscale",
        name="Tailscale remote LAN access",
        icon="mdi:lan-connect",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    GLiNetSwitchDescription(
        key="tailscale_wan_access_control",
        data_key="tailscale_wan_access",
        setting="wan_enabled",
        control="tailscale",
        name="Tailscale remote WAN access",
        icon="mdi:wan",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up GL.iNet switch controls."""
    coordinator: GLiNetCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        GLiNetControlSwitch(coordinator, entry, description)
        for description in SWITCHES
        if description.control in coordinator.data.capabilities
    )


class GLiNetControlSwitch(GLiNetEntity, SwitchEntity):
    """An allowlisted GL.iNet configuration switch."""

    entity_description: GLiNetSwitchDescription

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.binary.get(self.entity_description.data_key)

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        if self.entity_description.setting in {"lan_enabled", "wan_enabled"}:
            return bool(self.coordinator.data.binary.get("tailscale_enabled"))
        return self.entity_description.data_key in self.coordinator.data.binary

    async def _async_set(self, enabled: bool) -> None:
        description = self.entity_description
        if description.control == "tailscale" and description.setting:
            await self.coordinator.async_set_tailscale(description.setting, enabled)
        elif description.control == "adguard" and description.setting:
            await self.coordinator.async_set_adguard(description.setting, enabled)
        elif description.control == "led":
            await self.coordinator.async_set_led(enabled)
        elif description.control.startswith("wifi_") and description.setting:
            await self.coordinator.async_set_wifi_enabled(description.setting, enabled)
        else:
            raise ValueError(f"Unsupported control: {description.control}")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)
