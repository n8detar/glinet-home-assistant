from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import voluptuous as vol
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.glinet_router.api import GLiNetApiClient, GLiNetRpcError
from custom_components.glinet_router.button import BUTTONS, GLiNetButton
from custom_components.glinet_router.const import (
    CONF_USE_SSL,
    DOMAIN,
    EVENT_SMS_RECEIVED,
    SERVICE_SEND_SMS,
)
from custom_components.glinet_router.coordinator import GLiNetCoordinator
from custom_components.glinet_router.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.glinet_router.models import (
    RouterClient,
    RouterSnapshot,
    parse_sms_messages,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def sample_snapshot() -> RouterSnapshot:
    return RouterSnapshot(
        values={
            "uptime": 123,
            "cpu_temperature": 50,
            "multiwan_mode": "Failover",
            "internet_priority": "Cellular before Ethernet",
            "modem_bus": "0001:01:00.0",
            "cellular_rsrp": -100,
        },
        binary={
            "internet_connected": True,
            "cellular_connected": True,
            "repeater_healthy": True,
            "ethernet_1_healthy": False,
            "cellular_healthy": True,
            "tethering_healthy": False,
            "ethernet_2_healthy": True,
            "tailscale_enabled": False,
            "adguard_enabled": False,
            "adguard_dns_enabled": False,
        },
        device={
            "model": "x3000",
            "firmware": "4.8.3",
            "modem": "RM520N-GL",
        },
        capabilities={"router", "multiwan", "modem", "sms", "tailscale", "adguard"},
    )


async def test_setup_creates_entities_and_service(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        GLiNetApiClient, "async_get_snapshot", AsyncMock(return_value=sample_snapshot())
    )
    monkeypatch.setattr(
        GLiNetApiClient, "async_get_sms_messages", AsyncMock(return_value=[])
    )
    entry = MockConfigEntry(
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
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_SEND_SMS)
    assert hass.services.has_service(DOMAIN, "mark_sms_read")
    assert hass.services.has_service(DOMAIN, "delete_sms")
    assert hass.states.get("sensor.gl_x3000_uptime").state == "123"
    assert hass.states.get("binary_sensor.gl_x3000_internet").state == "on"
    assert hass.states.get("binary_sensor.gl_x3000_repeater_health").state == "on"
    assert hass.states.get("binary_sensor.gl_x3000_ethernet_1_health").state == "off"
    assert hass.states.get("select.gl_x3000_internet_priority").state == (
        "Cellular before Ethernet"
    )

    registry = er.async_get(hass)
    for unique_id in (
        "hashed-router-id_reboot_router",
        "hashed-router-id_reconnect_cellular",
        "hashed-router-id_mark_all_sms_read",
        "hashed-router-id_delete_all_read_sms",
    ):
        entity_id = registry.async_get_entity_id("button", DOMAIN, unique_id)
        assert entity_id is not None
        assert (
            registry.async_get(entity_id).disabled_by
            is er.RegistryEntryDisabler.INTEGRATION
        )

    assert await hass.config_entries.async_unload(entry.entry_id)
    for service in ("send_sms", "mark_sms_read", "delete_sms"):
        assert not hass.services.has_service(DOMAIN, service)


async def test_sms_message_services_route_message_id(hass, monkeypatch) -> None:
    monkeypatch.setattr(
        GLiNetApiClient, "async_get_snapshot", AsyncMock(return_value=sample_snapshot())
    )
    monkeypatch.setattr(
        GLiNetApiClient, "async_get_sms_messages", AsyncMock(return_value=[])
    )
    mark_read = AsyncMock()
    delete_sms = AsyncMock()
    monkeypatch.setattr(GLiNetApiClient, "async_mark_sms_read", mark_read)
    monkeypatch.setattr(GLiNetApiClient, "async_delete_sms", delete_sms)
    entry = MockConfigEntry(
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
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        "mark_sms_read",
        {"config_entry_id": entry.entry_id, "message_id": "sms-inbound-1"},
        blocking=True,
    )

    mark_read.assert_awaited_once_with(message_id="sms-inbound-1")

    await hass.services.async_call(
        DOMAIN,
        "delete_sms",
        {"config_entry_id": entry.entry_id, "message_id": "sms-inbound-1"},
        blocking=True,
    )

    delete_sms.assert_awaited_once_with(message_id="sms-inbound-1")

    for service in ("mark_sms_read", "delete_sms"):
        for invalid in ("   ", "x" * 129):
            with pytest.raises(vol.Invalid):
                await hass.services.async_call(
                    DOMAIN,
                    service,
                    {"message_id": invalid},
                    blocking=True,
                )
    mark_read.assert_awaited_once()
    delete_sms.assert_awaited_once()


async def test_sms_services_remain_until_last_config_entry_unloads(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        GLiNetApiClient, "async_get_snapshot", AsyncMock(return_value=sample_snapshot())
    )
    monkeypatch.setattr(
        GLiNetApiClient, "async_get_sms_messages", AsyncMock(return_value=[])
    )
    entries = []
    for suffix in ("one", "two"):
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=f"GL-X3000 {suffix}",
            unique_id=f"hashed-router-{suffix}",
            data={
                CONF_HOST: f"router-{suffix}.test",
                CONF_USERNAME: "root",
                CONF_PASSWORD: "private-password",
                CONF_USE_SSL: False,
                CONF_VERIFY_SSL: False,
            },
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        entries.append(entry)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entries[0].entry_id)
    for service in ("send_sms", "mark_sms_read", "delete_sms"):
        assert hass.services.has_service(DOMAIN, service)

    assert await hass.config_entries.async_unload(entries[1].entry_id)
    for service in ("send_sms", "mark_sms_read", "delete_sms"):
        assert not hass.services.has_service(DOMAIN, service)


async def test_config_entry_reload_rebaselines_sms_events(hass, monkeypatch) -> None:
    monkeypatch.setattr(
        GLiNetApiClient, "async_get_snapshot", AsyncMock(return_value=sample_snapshot())
    )
    existing = parse_sms_messages(
        {"list": [{"name": "existing", "body": "old", "type": 0, "status": 0}]}
    )
    with_new = [
        *existing,
        *parse_sms_messages(
            {"list": [{"name": "new", "body": "new", "type": 0, "status": 0}]}
        ),
    ]
    monkeypatch.setattr(
        GLiNetApiClient,
        "async_get_sms_messages",
        AsyncMock(side_effect=[existing, existing, with_new]),
    )
    entry = MockConfigEntry(
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
    )
    entry.add_to_hass(hass)
    events = []
    hass.bus.async_listen(EVENT_SMS_RECEIVED, events.append)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert events == []

    await entry.runtime_data.coordinator.async_request_refresh()
    await hass.async_block_till_done()
    assert [event.data["message_id"] for event in events] == ["new"]


async def test_failed_platform_setup_does_not_register_sms_services(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        GLiNetApiClient, "async_get_snapshot", AsyncMock(return_value=sample_snapshot())
    )
    monkeypatch.setattr(
        GLiNetApiClient, "async_get_sms_messages", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(side_effect=RuntimeError("platform setup failed")),
    )
    entry = MockConfigEntry(
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
    )
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.entry_id not in hass.data.get(DOMAIN, set())
    for service in ("send_sms", "mark_sms_read", "delete_sms"):
        assert not hass.services.has_service(DOMAIN, service)


async def test_sms_buttons_survive_initial_inbox_poll_failure(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        GLiNetApiClient, "async_get_snapshot", AsyncMock(return_value=sample_snapshot())
    )
    monkeypatch.setattr(
        GLiNetApiClient,
        "async_get_sms_messages",
        AsyncMock(side_effect=GLiNetRpcError(None, "temporary failure")),
    )
    entry = MockConfigEntry(
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
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    for unique_id in (
        "hashed-router-id_mark_all_sms_read",
        "hashed-router-id_delete_all_read_sms",
    ):
        assert registry.async_get_entity_id("button", DOMAIN, unique_id) is not None


async def test_sms_buttons_remain_unavailable_until_inbox_poll_succeeds(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="GL-X3000",
        unique_id="hashed-router-id",
    )
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.endpoint = "http://router.test/rpc"
    coordinator = GLiNetCoordinator(hass, entry, client)
    coordinator.data = RouterSnapshot(capabilities={"router", "sms"})
    coordinator.last_update_success = True
    description = next(item for item in BUTTONS if item.key == "mark_all_sms_read")
    button = GLiNetButton(coordinator, entry, description)

    assert not button.available

    coordinator.data.capabilities.add("sms_inbox")
    assert button.available


async def test_sms_bulk_buttons_route_to_coordinator_methods(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="GL-X3000",
        unique_id="hashed-router-id",
    )
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.endpoint = "http://router.test/rpc"
    coordinator = GLiNetCoordinator(hass, entry, client)
    coordinator.data = RouterSnapshot(capabilities={"router", "sms", "sms_inbox"})
    coordinator.last_update_success = True
    mark_all = AsyncMock()
    delete_all_read = AsyncMock()
    coordinator.async_mark_all_sms_read = mark_all
    coordinator.async_delete_all_read_sms = delete_all_read

    for key in ("mark_all_sms_read", "delete_all_read_sms"):
        description = next(item for item in BUTTONS if item.key == key)
        await GLiNetButton(coordinator, entry, description).async_press()

    mark_all.assert_awaited_once_with()
    delete_all_read.assert_awaited_once_with()


async def test_oversized_sms_is_rejected_before_router_io(hass, monkeypatch) -> None:
    monkeypatch.setattr(
        GLiNetApiClient, "async_get_snapshot", AsyncMock(return_value=sample_snapshot())
    )
    monkeypatch.setattr(
        GLiNetApiClient, "async_get_sms_messages", AsyncMock(return_value=[])
    )
    send_sms = AsyncMock()
    monkeypatch.setattr(GLiNetApiClient, "async_send_sms", send_sms)
    entry = MockConfigEntry(
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
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "send_sms",
            {"phone_number": "+1XXXXXXXXXX", "message": "x" * 161},
            blocking=True,
        )

    send_sms.assert_not_awaited()


async def test_diagnostics_are_allowlisted(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="GL-X3000",
        unique_id="hashed-router-id",
        data={
            CONF_HOST: "private-router.test",
            CONF_USERNAME: "root",
            CONF_PASSWORD: "private-password",
            CONF_USE_SSL: False,
            CONF_VERIFY_SSL: False,
        },
    )
    snapshot = sample_snapshot()
    snapshot.values["modem_bus"] = "private-bus"
    snapshot.clients["00:11:22:33:44:55"] = RouterClient(
        mac="00:11:22:33:44:55",
        name="private-client",
        ip_address="192.0.2.80",
        connected=True,
        interface="5G",
        blocked=False,
        remote=False,
    )
    entry.runtime_data = type(
        "Runtime",
        (),
        {
            "coordinator": type(
                "Coordinator",
                (),
                {"data": snapshot, "last_update_success": True},
            )()
        },
    )()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    serialized = repr(diagnostics)

    assert diagnostics["device"]["model"] == "x3000"
    for private in (
        "private-router.test",
        "private-password",
        "private-bus",
        "private-client",
        "00:11:22:33:44:55",
        "192.0.2.80",
        "root",
    ):
        assert private not in serialized
