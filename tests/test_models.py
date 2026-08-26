from __future__ import annotations

from custom_components.glinet_router.models import (
    PRIORITY_CELLULAR_FIRST,
    PRIORITY_ETHERNET_FIRST,
    build_failover_payload,
    build_snapshot,
)


def test_build_snapshot_normalizes_clients_while_excluding_router_secrets() -> None:
    responses = {
        "system_info": {
            "model": "GL-X3000",
            "firmware_version": "4.8.3",
            "mac": "AA:BB:CC:DD:EE:FF",
            "serial": "private-serial",
        },
        "system_status": {
            "system": {
                "uptime": 1234,
                "cpu": {"temperature": 55},
                "load_average": [0.1, 0.2, 0.3],
                "memory_total": 1000,
                "memory_free": 100,
                "memory_buff_cache": 400,
                "flash_total": 2000,
                "flash_free": 500,
            },
            "client": [{"wireless_total": 2, "cable_total": 1}],
            "service": [{"name": "tailscale", "status": 1}],
        },
        "fan_status": {"speed": 1200, "status": True},
        "led_config": {"led_enable": True},
        "kmwan_config": {
            "mode": 0,
            "interfaces": [
                {"interface": "wwan", "metric": 1},
                {"interface": "modem_0001", "metric": 2},
                {"interface": "wan", "metric": 3},
                {"interface": "tethering", "metric": 4},
                {"interface": "secondwan", "metric": 5},
            ],
        },
        "kmwan_status": [
            {"interface": "wwan", "status_v4": 0, "status_v6": 1},
            {"interface": "wan", "status_v4": 1, "status_v6": 1},
            {"interface": "modem_0001", "status_v4": 0, "status_v6": 1},
        ],
        "modem_info": {
            "modems": [
                {
                    "bus": "0001:01:00.0",
                    "model": "RM520N-GL",
                    "name": "RM520NGLAAR03A03M4G",
                    "imei": "private-imei",
                    "simcard": {"iccid": "private-iccid", "imsi": "private-imsi"},
                }
            ]
        },
        "modem_status": {
            "new_sms_count": 3,
            "modems": [
                {
                    "bus": "0001:01:00.0",
                    "current_sim": "1",
                    "simcard": {
                        "carrier": "Example Carrier",
                        "signal": {
                            "network_type": "NR5G-NSA",
                            "rsrp": -100,
                            "rsrq": -12,
                            "sinr": 11,
                            "rssi": -75,
                        },
                    },
                    "network": {"status": 0, "traffic_total": "123456"},
                }
            ],
        },
        "cells_info": {
            "cells": [
                {
                    "id": "location-sensitive-cell",
                    "mode": "LTE FDD",
                    "band": 66,
                    "dl_bandwidth": "20M",
                    "type": "servingcell",
                },
                {
                    "mode": "NR5G-NSA",
                    "band": 41,
                    "dl_bandwidth": "100M",
                    "type": "servingcell",
                },
            ]
        },
        "tailscale_config": {
            "enabled": True,
            "lan_enabled": True,
            "wan_enabled": False,
            "lan_ip": "192.168.8.0/24",
        },
        "tailscale_status": {
            "status": 3,
            "login_name": "private@example.com",
            "address_v4": "100.64.0.1",
        },
        "vpn_tunnel": {"global_enabled": False, "tunnels": []},
        "adguard_config": {"enabled": False, "dns_enabled": False},
        "firewall_rules": {"res": [{"name": "private-rule"}]},
        "port_forwards": {"res": [{"dest_ip": "192.168.8.20"}]},
        "clients": {
            "clients": [
                {
                    "online": True,
                    "iface": "5G",
                    "name": "private-phone",
                    "mac": "11:22:33:44:55:66",
                    "ip": "192.168.8.20",
                }
            ]
        },
    }

    snapshot = build_snapshot(responses)

    assert snapshot.values["uptime"] == 1234
    assert snapshot.values["memory_usage"] == 50.0
    assert snapshot.values["flash_usage"] == 75.0
    assert snapshot.values["fan_rpm"] == 1200
    assert snapshot.values["active_wan"] == "Repeater"
    assert snapshot.values["internet_priority"] == PRIORITY_CELLULAR_FIRST
    assert snapshot.values["cellular_bands"] == "LTE B66 + NR5G-NSA n41"
    assert snapshot.values["cellular_traffic_total"] == 123456
    assert snapshot.values["online_clients"] == 1
    assert snapshot.values["firewall_rules"] == 1
    assert snapshot.values["port_forwards"] == 1
    assert snapshot.binary["internet_connected"] is True
    assert snapshot.binary["repeater_healthy"] is True
    assert snapshot.binary["ethernet_1_healthy"] is False
    assert snapshot.binary["cellular_connected"] is True
    assert snapshot.binary["led_enabled"] is True
    assert snapshot.binary["tailscale_connected"] is True
    assert "led" in snapshot.capabilities
    client = snapshot.clients["11:22:33:44:55:66"]
    assert client.name == "private-phone"
    assert client.ip_address == "192.168.8.20"
    assert client.interface == "5G"
    assert client.connected is True

    serialized = repr(snapshot)
    for private_value in (
        "AA:BB:CC:DD:EE:FF",
        "private-serial",
        "private-imei",
        "private-iccid",
        "private-imsi",
        "location-sensitive-cell",
        "private@example.com",
        "100.64.0.1",
        "private-rule",
    ):
        assert private_value not in serialized


def test_build_failover_payload_matches_router_ui() -> None:
    assert build_failover_payload(PRIORITY_ETHERNET_FIRST) == {
        "mode": 0,
        "interfaces": [
            {"interface": "wwan", "metric": 1},
            {"interface": "wan", "metric": 2},
            {"interface": "modem_0001", "metric": 3},
            {"interface": "tethering", "metric": 4},
            {"interface": "secondwan", "metric": 5},
        ],
    }
    assert build_failover_payload(PRIORITY_CELLULAR_FIRST)["interfaces"][1] == {
        "interface": "modem_0001",
        "metric": 2,
    }
