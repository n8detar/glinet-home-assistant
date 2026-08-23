"""Diagnostics for the GL.iNet Router integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import GLiNetConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GLiNetConfigEntry
) -> dict[str, Any]:
    """Return an explicit allowlist; never serialize raw API responses."""
    snapshot = entry.runtime_data.coordinator.data
    values = {
        key: value for key, value in snapshot.values.items() if key not in {"modem_bus"}
    }
    return {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "options": dict(entry.options),
            "use_ssl": bool(entry.data.get("use_ssl", False)),
            "verify_ssl": bool(entry.data.get("verify_ssl", False)),
        },
        "device": dict(snapshot.device),
        "values": values,
        "binary": dict(snapshot.binary),
        "capabilities": sorted(snapshot.capabilities),
        "last_update_success": entry.runtime_data.coordinator.last_update_success,
    }
