"""Privacy-safe data models for the GL.iNet Router integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

PRIORITY_ETHERNET_FIRST: Final = "Ethernet before cellular"
PRIORITY_CELLULAR_FIRST: Final = "Cellular before Ethernet"
PRIORITY_OPTIONS: Final = (PRIORITY_ETHERNET_FIRST, PRIORITY_CELLULAR_FIRST)

_ETHERNET_FIRST = ("wwan", "wan", "modem_0001", "tethering", "secondwan")
_CELLULAR_FIRST = ("wwan", "modem_0001", "wan", "tethering", "secondwan")
_INTERFACE_NAMES: Final = {
    "wwan": "Repeater",
    "wan": "Ethernet 1",
    "modem_0001": "Cellular",
    "tethering": "Tethering",
    "secondwan": "Ethernet 2",
}
_INTERFACE_HEALTH_KEYS: Final = {
    "wwan": "repeater_healthy",
    "wan": "ethernet_1_healthy",
    "modem_0001": "cellular_healthy",
    "tethering": "tethering_healthy",
    "secondwan": "ethernet_2_healthy",
}
_MODEM_MODEL_PREFIXES: Final = {
    "RM520NGL": "RM520N-GL",
}


@dataclass(slots=True)
class RouterSnapshot:
    """Sanitized coordinator data. Raw RPC responses must never be stored here."""

    values: dict[str, Any] = field(default_factory=dict)
    binary: dict[str, bool | None] = field(default_factory=dict)
    device: dict[str, str] = field(default_factory=dict)
    capabilities: set[str] = field(default_factory=set)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> int | float | None:
    return (
        value
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else None
    )


def _modem_model(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    for prefix, model in _MODEM_MODEL_PREFIXES.items():
        if value.upper().startswith(prefix):
            return model
    return value


def _percent_used(total: Any, free: Any, cache: Any = 0) -> float | None:
    total_value = _number(total)
    free_value = _number(free)
    cache_value = _number(cache) or 0
    if total_value is None or free_value is None or total_value <= 0:
        return None
    used = max(0, total_value - free_value - cache_value)
    return round(used / total_value * 100, 1)


def _priority_from_config(config: dict[str, Any]) -> str | None:
    if config.get("mode") != 0:
        return None
    interfaces = [
        item for item in _list(config.get("interfaces")) if isinstance(item, dict)
    ]
    order = tuple(
        str(item.get("interface"))
        for item in sorted(interfaces, key=lambda item: item.get("metric", 999))
    )
    if order == _ETHERNET_FIRST:
        return PRIORITY_ETHERNET_FIRST
    if order == _CELLULAR_FIRST:
        return PRIORITY_CELLULAR_FIRST
    return None


def build_failover_payload(option: str) -> dict[str, Any]:
    """Build the same complete metric payload as the GL.iNet frontend."""
    if option == PRIORITY_ETHERNET_FIRST:
        order = _ETHERNET_FIRST
    elif option == PRIORITY_CELLULAR_FIRST:
        order = _CELLULAR_FIRST
    else:
        raise ValueError(f"Unsupported internet priority: {option}")
    return {
        "mode": 0,
        "interfaces": [
            {"interface": interface, "metric": index}
            for index, interface in enumerate(order, start=1)
        ],
    }


def _cellular_bands(cells: list[Any]) -> str | None:
    labels: list[str] = []
    for raw_cell in cells:
        cell = _dict(raw_cell)
        mode = str(cell.get("mode", ""))
        band = cell.get("band")
        if not mode or band is None:
            continue
        prefix = "n" if mode.startswith("NR") else "B"
        display_mode = "LTE" if mode.startswith("LTE") else mode
        labels.append(f"{display_mode} {prefix}{band}")
    return " + ".join(labels) or None


def build_snapshot(responses: dict[str, Any]) -> RouterSnapshot:
    """Convert raw responses to a compact, privacy-safe coordinator snapshot."""
    snapshot = RouterSnapshot()
    values = snapshot.values
    binary = snapshot.binary

    info = _dict(responses.get("system_info"))
    if info:
        snapshot.capabilities.add("router")
    snapshot.device = {
        key: str(value)
        for key, value in {
            "model": info.get("model"),
            "firmware": info.get("firmware_version") or info.get("version"),
        }.items()
        if value not in (None, "")
    }

    status = _dict(responses.get("system_status"))
    system = _dict(status.get("system"))
    values.update(
        {
            "uptime": _number(system.get("uptime")),
            "cpu_temperature": _number(_dict(system.get("cpu")).get("temperature")),
            "memory_usage": _percent_used(
                system.get("memory_total"),
                system.get("memory_free"),
                system.get("memory_buff_cache"),
            ),
            "memory_free": _number(system.get("memory_free")),
            "memory_total": _number(system.get("memory_total")),
            "flash_usage": _percent_used(
                system.get("flash_total"), system.get("flash_free")
            ),
            "flash_free": _number(system.get("flash_free")),
            "flash_total": _number(system.get("flash_total")),
            "router_mode": system.get("mode"),
            "ipv6_enabled": system.get("ipv6_enabled"),
        }
    )
    binary["time_synchronized"] = system.get("time_sync_status")
    binary["qos_enabled"] = bool(system.get("qos_enabled"))
    binary["sqm_enabled"] = bool(system.get("sqm_enabled"))
    load_average = _list(system.get("load_average"))
    if len(load_average) >= 3:
        values["load_1m"], values["load_5m"], values["load_15m"] = load_average[:3]

    client_summary = (
        _dict(_list(status.get("client"))[0]) if _list(status.get("client")) else {}
    )
    values["wireless_clients"] = client_summary.get("wireless_total", 0)
    values["wired_clients"] = client_summary.get("cable_total", 0)
    values["online_clients"] = values["wireless_clients"] + values["wired_clients"]

    services = {
        item.get("name"): item.get("status")
        for item in _list(status.get("service"))
        if isinstance(item, dict)
    }
    for service_name in ("wgserver", "ovpnserver", "tor", "zerotier"):
        if service_name in services:
            binary[f"service_{service_name}_running"] = services[service_name] == 1

    for raw_interface in _list(status.get("network")):
        interface = _dict(raw_interface)
        name = interface.get("interface")
        if isinstance(name, str) and not name.endswith("6"):
            binary[f"interface_{name}_up"] = bool(interface.get("up"))
            binary[f"interface_{name}_online"] = bool(interface.get("online"))

    wifi_radios = [item for item in _list(status.get("wifi")) if isinstance(item, dict)]
    values["wifi_radios_enabled"] = sum(bool(item.get("up")) for item in wifi_radios)
    values["wifi_radios_total"] = len(wifi_radios)
    for band in ("2G", "5G"):
        matching = [
            item
            for item in wifi_radios
            if item.get("band") == band and not item.get("guest")
        ]
        if matching:
            binary[f"wifi_{band.lower()}_enabled"] = any(
                bool(item.get("up")) for item in matching
            )

    fan = _dict(responses.get("fan_status"))
    values["fan_rpm"] = _number(fan.get("speed"))
    binary["fan_running"] = bool(fan.get("status"))

    kmwan_config = _dict(responses.get("kmwan_config"))
    if kmwan_config.get("interfaces"):
        snapshot.capabilities.add("multiwan")
    values["multiwan_mode"] = (
        "Failover"
        if kmwan_config.get("mode") == 0
        else "Load balancing"
        if kmwan_config.get("mode") == 1
        else None
    )
    values["internet_priority"] = _priority_from_config(kmwan_config)
    sensitivity = _dict(responses.get("kmwan_sensitivity"))
    sensitivity_value = _dict(sensitivity.get("sensitivity"))
    values["multiwan_sensitivity"] = sensitivity_value.get("level")

    raw_kmwan_status = responses.get("kmwan_status")
    status_interfaces = (
        raw_kmwan_status
        if isinstance(raw_kmwan_status, list)
        else _list(_dict(raw_kmwan_status).get("interfaces"))
    )
    health = {
        str(item.get("interface")): item.get("status_v4") == 0
        for item in status_interfaces
        if isinstance(item, dict) and item.get("interface")
    }
    for interface, healthy in health.items():
        if key := _INTERFACE_HEALTH_KEYS.get(interface):
            binary[key] = healthy
    metrics = {
        str(item.get("interface")): item.get("metric", 999)
        for item in _list(kmwan_config.get("interfaces"))
        if isinstance(item, dict) and item.get("interface")
    }
    healthy_interfaces = sorted(
        (interface for interface, healthy in health.items() if healthy),
        key=lambda interface: metrics.get(interface, 999),
    )
    values["active_wan"] = (
        _INTERFACE_NAMES.get(healthy_interfaces[0], healthy_interfaces[0])
        if healthy_interfaces
        else None
    )
    binary["internet_connected"] = bool(healthy_interfaces)

    modem_info = _dict(responses.get("modem_info"))
    modem_descriptions = _list(modem_info.get("modems"))
    if modem_descriptions:
        modem_description = _dict(modem_descriptions[0])
        modem_model = _modem_model(
            modem_description.get("model") or modem_description.get("name")
        )
        if modem_model:
            snapshot.device["modem"] = str(modem_model)
        if modem_description.get("bus"):
            values["modem_bus"] = str(modem_description["bus"])
            snapshot.capabilities.add("modem")
        if modem_description.get("sms_support"):
            snapshot.capabilities.add("sms")

    modem_status = _dict(responses.get("modem_status"))
    values["unread_sms"] = modem_status.get("new_sms_count", 0)
    modems = _list(modem_status.get("modems"))
    if modems:
        modem = _dict(modems[0])
        simcard = _dict(modem.get("simcard"))
        signal = _dict(simcard.get("signal"))
        network = _dict(modem.get("network"))
        values.update(
            {
                "active_sim": modem.get("current_sim"),
                "cellular_carrier": simcard.get("carrier"),
                "cellular_network_type": signal.get("network_type"),
                "cellular_rsrp": _number(signal.get("rsrp")),
                "cellular_rsrq": _number(signal.get("rsrq")),
                "cellular_sinr": _number(signal.get("sinr")),
                "cellular_rssi": _number(signal.get("rssi")),
            }
        )
        traffic = network.get("traffic_total")
        try:
            values["cellular_traffic_total"] = (
                int(traffic) if traffic not in (None, "") else None
            )
        except (TypeError, ValueError):
            values["cellular_traffic_total"] = None
        binary["cellular_connected"] = network.get("status") == 0

    cells = _list(_dict(responses.get("cells_info")).get("cells"))
    values["cellular_bands"] = _cellular_bands(cells)
    values["cellular_downlink_bandwidth"] = (
        " + ".join(
            str(_dict(cell).get("dl_bandwidth"))
            for cell in cells
            if _dict(cell).get("dl_bandwidth")
        )
        or None
    )

    tailscale_config = _dict(responses.get("tailscale_config"))
    tailscale_status = _dict(responses.get("tailscale_status"))
    if tailscale_config or tailscale_status:
        snapshot.capabilities.add("tailscale")
    binary["tailscale_enabled"] = bool(tailscale_config.get("enabled"))
    binary["tailscale_connected"] = tailscale_status.get("status") == 3
    binary["tailscale_lan_access"] = bool(tailscale_config.get("lan_enabled"))
    binary["tailscale_wan_access"] = bool(tailscale_config.get("wan_enabled"))
    values["tailscale_status_code"] = tailscale_status.get("status")

    vpn = _dict(responses.get("vpn_tunnel"))
    if vpn:
        snapshot.capabilities.add("vpn")
    binary["vpn_client_enabled"] = bool(vpn.get("global_enabled"))
    values["vpn_tunnels"] = len(_list(vpn.get("tunnels")))

    adguard = _dict(responses.get("adguard_config"))
    if adguard:
        snapshot.capabilities.add("adguard")
    binary["adguard_enabled"] = bool(adguard.get("enabled"))
    binary["adguard_dns_enabled"] = bool(adguard.get("dns_enabled"))
    binary["adguard_running"] = services.get("adguard") == 1

    raw_firewall_rules = _dict(responses.get("firewall_rules"))
    raw_port_forwards = _dict(responses.get("port_forwards"))
    if raw_firewall_rules or raw_port_forwards:
        snapshot.capabilities.add("firewall")
    firewall_rules = _list(raw_firewall_rules.get("res"))
    port_forwards = _list(raw_port_forwards.get("res"))
    values["firewall_rules"] = len(firewall_rules)
    values["port_forwards"] = len(port_forwards)

    raw_clients = _list(_dict(responses.get("clients")).get("clients"))
    if raw_clients:
        online_clients = [
            client
            for client in raw_clients
            if isinstance(client, dict) and client.get("online")
        ]
        values["online_clients"] = len(online_clients)
        values["online_2g_clients"] = sum(
            _dict(client).get("iface") == "2.4G" for client in online_clients
        )
        values["online_5g_clients"] = sum(
            _dict(client).get("iface") == "5G" for client in online_clients
        )
        values["online_wired_clients"] = sum(
            _dict(client).get("iface") == "cable" for client in online_clients
        )

    ddns_config = _dict(responses.get("ddns_config"))
    ddns_status = _dict(responses.get("ddns_status"))
    if ddns_config or ddns_status:
        snapshot.capabilities.add("ddns")
    binary["ddns_enabled"] = bool(
        ddns_config.get("enable_ddns", ddns_config.get("enabled"))
    )
    values["ddns_status_code"] = ddns_status.get("status")

    zerotier_config = _dict(responses.get("zerotier_config"))
    zerotier_status = _dict(responses.get("zerotier_status"))
    if zerotier_config or zerotier_status:
        snapshot.capabilities.add("zerotier")
    binary["zerotier_enabled"] = bool(zerotier_config.get("enabled"))
    values["zerotier_status_code"] = zerotier_status.get("status")

    return snapshot
