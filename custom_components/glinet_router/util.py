"""Small pure helpers for the GL.iNet Router integration."""

from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import urlparse


def build_endpoint(host: str, *, use_ssl: bool) -> str:
    """Normalize a host or URL to the firmware JSON-RPC endpoint."""
    value = host.strip().rstrip("/")
    if "://" not in value:
        value = f"{'https' if use_ssl else 'http'}://{value}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid router host")
    return f"{parsed.scheme}://{parsed.netloc}/rpc"


def router_unique_id(system_info: dict[str, Any], host: str) -> str:
    """Hash a stable router identifier before storing it as the unique ID."""
    seed = (
        system_info.get("serial")
        or system_info.get("serial_number")
        or system_info.get("mac")
        or system_info.get("mac_address")
        or host.lower()
    )
    return hashlib.sha256(str(seed).encode()).hexdigest()[:20]
