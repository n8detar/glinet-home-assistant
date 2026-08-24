from __future__ import annotations

from custom_components.glinet_router.models import (
    ClientPresenceStore,
    RouterClient,
    build_snapshot,
)


def test_client_inventory_is_normalized_and_drops_traffic_history() -> None:
    snapshot = build_snapshot(
        {
            "clients": {
                "clients": [
                    {
                        "mac": "72-c7-1c-88-a6-2b",
                        "ip": "192.0.2.10",
                        "name": "Test phone",
                        "online": True,
                        "iface": "5G",
                        "blocked": False,
                        "remote": False,
                        "last_rx": ["private-history"],
                        "last_tx": ["private-history"],
                        "total_rx": "123456",
                        "total_tx": "654321",
                    },
                    {
                        "mac": "invalid",
                        "name": "Invalid client",
                        "online": True,
                    },
                ]
            }
        }
    )

    assert snapshot.capabilities == {"clients"}
    assert snapshot.clients == {
        "72:C7:1C:88:A6:2B": RouterClient(
            mac="72:C7:1C:88:A6:2B",
            name="Test phone",
            ip_address="192.0.2.10",
            connected=True,
            interface="5G",
            blocked=False,
            remote=False,
        )
    }
    assert "private-history" not in repr(snapshot)
    assert "123456" not in repr(snapshot)
    assert "654321" not in repr(snapshot)


def test_duplicate_client_prefers_online_record() -> None:
    snapshot = build_snapshot(
        {
            "clients": {
                "clients": [
                    {
                        "mac": "72:C7:1C:88:A6:2B",
                        "name": "Offline name",
                        "online": False,
                        "iface": "5G",
                    },
                    {
                        "mac": "72-c7-1c-88-a6-2b",
                        "name": "Online name",
                        "online": True,
                        "iface": "5G",
                    },
                ]
            }
        }
    )

    assert snapshot.clients["72:C7:1C:88:A6:2B"].connected is True
    assert snapshot.clients["72:C7:1C:88:A6:2B"].name == "Online name"


def test_presence_store_applies_stale_grace_period_and_remembers_clients() -> None:
    client = RouterClient(
        mac="72:C7:1C:88:A6:2B",
        name="Phone",
        ip_address="192.0.2.10",
        connected=True,
        interface="5G",
        blocked=False,
        remote=False,
    )
    store = ClientPresenceStore(detection_time=300)

    first = store.update({client.mac: client}, now=1000)
    assert first[client.mac].connected is True

    offline = RouterClient(
        mac=client.mac,
        name="Phone",
        ip_address="192.0.2.10",
        connected=False,
        interface="5G",
        blocked=False,
        remote=False,
    )
    within_grace = store.update({client.mac: offline}, now=1299)
    assert within_grace[client.mac].connected is True

    expired = store.update({}, now=1301)
    assert expired[client.mac].connected is False
    assert expired[client.mac].name == "Phone"


def test_presence_store_retains_initial_offline_client_as_not_connected() -> None:
    client = RouterClient(
        mac="00:11:22:33:44:66",
        name="Historical",
        ip_address="192.0.2.30",
        connected=False,
        interface="5G",
        blocked=False,
        remote=False,
    )

    clients = ClientPresenceStore(detection_time=300).update(
        {client.mac: client}, now=1000
    )

    assert clients == {client.mac: client}


def test_presence_store_filters_wired_and_optional_local_macs() -> None:
    wired = RouterClient(
        mac="00:11:22:33:44:55",
        name="Desktop",
        ip_address="192.0.2.20",
        connected=True,
        interface="cable",
        blocked=False,
        remote=False,
    )
    local_wireless = RouterClient(
        mac="72:C7:1C:88:A6:2B",
        name="Private address",
        ip_address="192.0.2.21",
        connected=True,
        interface="5G",
        blocked=False,
        remote=False,
    )
    store = ClientPresenceStore(
        detection_time=300,
        include_wired=False,
        ignore_local_mac=True,
    )

    assert (
        store.update({wired.mac: wired, local_wireless.mac: local_wireless}, now=1000)
        == {}
    )
