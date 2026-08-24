from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.glinet_router.api import GLiNetApiClient
from custom_components.glinet_router.const import (
    CONF_TRACK_CLIENTS,
    CONF_USE_SSL,
    DOMAIN,
)
from custom_components.glinet_router.models import RouterClient, RouterSnapshot

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _client(
    mac: str,
    name: str,
    *,
    connected: bool = True,
    interface: str = "5G",
    ip_address: str = "192.0.2.10",
) -> RouterClient:
    return RouterClient(
        mac=mac,
        name=name,
        ip_address=ip_address,
        connected=connected,
        interface=interface,
        blocked=False,
        remote=False,
    )


def _snapshot(*clients: RouterClient) -> RouterSnapshot:
    return RouterSnapshot(
        device={"model": "GL-X3000", "firmware": "4.8.3"},
        capabilities={"router", "clients"},
        clients={client.mac: client for client in clients},
    )


def _entry(*, options: dict | None = None) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="GL-X3000",
        unique_id="hashed-router-id",
        data={
            CONF_HOST: "router.test",
            CONF_USERNAME: "root",
            CONF_PASSWORD: "private-password",
            CONF_USE_SSL: False,
            CONF_VERIFY_SSL: False,
        },
        options=options or {},
    )


async def test_setup_creates_unifi_style_client_trackers_without_devices(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    phone = _client("72:C7:1C:88:A6:2B", "Phone")
    desktop = _client(
        "00:11:22:33:44:55",
        "Desktop",
        interface="cable",
        ip_address="192.0.2.20",
    )
    historical = _client(
        "00:11:22:33:44:66",
        "Historical",
        connected=False,
        ip_address="192.0.2.30",
    )
    get_snapshot = AsyncMock(return_value=_snapshot(phone, desktop, historical))
    monkeypatch.setattr(GLiNetApiClient, "async_get_snapshot", get_snapshot)
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    phone_entity_id = registry.async_get_entity_id(
        "device_tracker",
        DOMAIN,
        "hashed-router-id_client_72:C7:1C:88:A6:2B",
    )
    desktop_entity_id = registry.async_get_entity_id(
        "device_tracker",
        DOMAIN,
        "hashed-router-id_client_00:11:22:33:44:55",
    )
    historical_entity_id = registry.async_get_entity_id(
        "device_tracker",
        DOMAIN,
        "hashed-router-id_client_00:11:22:33:44:66",
    )

    tracker_entries = [
        entity
        for entity in registry.entities.values()
        if entity.platform == DOMAIN and entity.domain == "device_tracker"
    ]
    assert phone_entity_id is not None, [entity.unique_id for entity in tracker_entries]
    assert desktop_entity_id is not None
    assert historical_entity_id is None

    phone_state = hass.states.get(phone_entity_id)
    assert phone_state is not None
    assert phone_state.state == "home"
    assert phone_state.attributes["source_type"] == "router"
    assert phone_state.attributes["mac"] == phone.mac
    assert phone_state.attributes["ip"] == phone.ip_address
    assert phone_state.attributes["host_name"] == "Phone"
    assert phone_state.attributes["connection_type"] == "wireless"
    assert phone_state.attributes["interface"] == "5G"

    phone_registry_entry = registry.async_get(phone_entity_id)
    assert phone_registry_entry is not None
    assert phone_registry_entry.device_id is None
    assert get_snapshot.await_args.kwargs == {"include_clients": True}


async def test_new_clients_are_added_after_a_coordinator_refresh(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    phone = _client("72:C7:1C:88:A6:2B", "Phone")
    tablet = _client(
        "00:11:22:33:44:77",
        "Tablet",
        ip_address="192.0.2.40",
    )
    get_snapshot = AsyncMock(
        side_effect=[
            _snapshot(phone),
            _snapshot(phone, tablet),
        ]
    )
    monkeypatch.setattr(GLiNetApiClient, "async_get_snapshot", get_snapshot)
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    tablet_entity_id = registry.async_get_entity_id(
        "device_tracker",
        DOMAIN,
        "hashed-router-id_client_00:11:22:33:44:77",
    )
    assert tablet_entity_id is not None
    tablet_state = hass.states.get(tablet_entity_id)
    assert tablet_state is not None
    assert tablet_state.state == "home"


async def test_existing_tracker_loads_not_home_when_client_is_missing_after_reload(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    phone = _client("72:C7:1C:88:A6:2B", "Phone")
    get_snapshot = AsyncMock(return_value=_snapshot(phone))
    monkeypatch.setattr(GLiNetApiClient, "async_get_snapshot", get_snapshot)
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "device_tracker",
        DOMAIN,
        "hashed-router-id_client_72:C7:1C:88:A6:2B",
    )
    assert entity_id is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    get_snapshot.return_value = _snapshot()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "not_home"


async def test_tracker_expires_after_stale_grace_period(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    phone = _client("72:C7:1C:88:A6:2B", "Phone")
    get_snapshot = AsyncMock(
        side_effect=[
            _snapshot(phone),
            _snapshot(),
            _snapshot(),
        ]
    )
    now = [1000.0]
    monkeypatch.setattr(GLiNetApiClient, "async_get_snapshot", get_snapshot)
    monkeypatch.setattr(
        "custom_components.glinet_router.coordinator.monotonic", lambda: now[0]
    )
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "device_tracker",
        DOMAIN,
        "hashed-router-id_client_72:C7:1C:88:A6:2B",
    )
    assert entity_id is not None

    now[0] = 1200.0
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "home"

    now[0] = 1301.0
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "not_home"


async def test_existing_entity_registry_disabled_choice_is_preserved(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    phone = _client("72:C7:1C:88:A6:2B", "Phone")
    get_snapshot = AsyncMock(return_value=_snapshot(phone))
    monkeypatch.setattr(GLiNetApiClient, "async_get_snapshot", get_snapshot)
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "device_tracker",
        DOMAIN,
        "hashed-router-id_client_72:C7:1C:88:A6:2B",
    )
    assert entity_id is not None
    registry.async_update_entity(entity_id, disabled_by=er.RegistryEntryDisabler.USER)

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry_entry = registry.async_get(entity_id)
    assert registry_entry is not None
    assert registry_entry.disabled_by is er.RegistryEntryDisabler.USER
    assert hass.states.get(entity_id) is None


async def test_disabling_client_tracking_skips_inventory_and_entities(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    get_snapshot = AsyncMock(return_value=_snapshot())
    monkeypatch.setattr(GLiNetApiClient, "async_get_snapshot", get_snapshot)
    entry = _entry(options={CONF_TRACK_CLIENTS: False})
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert get_snapshot.await_args.kwargs == {"include_clients": False}
    registry = er.async_get(hass)
    assert not [
        entity
        for entity in registry.entities.values()
        if entity.platform == DOMAIN and entity.domain == "device_tracker"
    ]
