import json
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.glinet_router import GLiNetRuntimeData
from custom_components.glinet_router.api import GLiNetRpcError
from custom_components.glinet_router.const import DOMAIN, EVENT_SMS_RECEIVED
from custom_components.glinet_router.coordinator import GLiNetCoordinator
from custom_components.glinet_router.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.glinet_router.models import (
    RouterSnapshot,
    SmsInboxTracker,
    parse_sms_messages,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def test_parse_sms_messages_normalizes_verified_fields() -> None:
    messages = parse_sms_messages(
        {
            "list": [
                {
                    "name": "sms-inbound-1",
                    "phone_number": "+155****0100",
                    "sender": "Test sender",
                    "body": "Private test body",
                    "date": "2026-08-24 10:00:00",
                    "type": 0,
                    "status": 0,
                    "bus": "0001:01:00.0",
                    "ignored": "not retained",
                },
                {"body": "missing identifier", "type": 0, "status": 0},
                {
                    "name": "x" * 129,
                    "body": "Overlong identifier must not become an event",
                    "type": 0,
                    "status": 0,
                },
            ]
        }
    )

    assert len(messages) == 1
    message = messages[0]
    assert message.message_id == "sms-inbound-1"
    assert message.sender == "Test sender"
    assert message.message == "Private test body"
    assert message.date == "2026-08-24 10:00:00"
    assert message.message_type == 0
    assert message.status == 0
    representation = repr(message)
    assert "ignored" not in representation
    assert "0001:01:00.0" not in representation
    assert "Private test body" not in representation
    assert "Test sender" not in representation
    assert "2026-08-24 10:00:00" not in representation


def test_sms_inbox_tracker_suppresses_startup_and_emits_new_inbound_once() -> None:
    tracker = SmsInboxTracker()
    initial = parse_sms_messages(
        {"list": [{"name": "existing", "body": "old", "type": 0, "status": 0}]}
    )
    current = parse_sms_messages(
        {
            "list": [
                {"name": "existing", "body": "old", "type": 0, "status": 0},
                {"name": "new-inbound", "body": "new", "type": 0, "status": 0},
                {"name": "new-inbound", "body": "duplicate", "type": 0, "status": 0},
                {"name": "new-outbound", "body": "sent", "type": 1, "status": 2},
            ]
        }
    )

    assert tracker.process(initial) == []
    assert [message.message_id for message in tracker.process(current)] == [
        "new-inbound"
    ]
    assert tracker.process(current) == []


async def test_coordinator_fires_received_event_without_retaining_message(
    hass, caplog
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="router-id")
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_get_snapshot.side_effect = [
        RouterSnapshot(capabilities={"router", "sms"}),
        RouterSnapshot(capabilities={"router", "sms"}),
    ]
    client.async_get_sms_messages.side_effect = [
        parse_sms_messages(
            {"list": [{"name": "existing", "body": "old", "type": 0, "status": 0}]}
        ),
        parse_sms_messages(
            {
                "list": [
                    {"name": "existing", "body": "old", "type": 0, "status": 0},
                    {
                        "name": "new-inbound",
                        "phone_number": "+155****0100",
                        "body": "Private event body",
                        "date": "2026-08-24 10:00:00",
                        "type": 0,
                        "status": 0,
                    },
                ]
            }
        ),
    ]
    events = []
    hass.bus.async_listen(EVENT_SMS_RECEIVED, events.append)
    coordinator = GLiNetCoordinator(hass, entry, client)

    first = await coordinator._async_update_data()
    second = await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert "sms_inbox" in first.capabilities
    assert "sms_inbox" in second.capabilities
    assert [event.data for event in events] == [
        {
            "config_entry_id": entry.entry_id,
            "message_id": "new-inbound",
            "from": "+155****0100",
            "message": "Private event body",
            "date": "2026-08-24 10:00:00",
        }
    ]
    assert "Private event body" not in repr(second)
    assert "+155****0100" not in repr(second)
    assert "Private event body" not in repr(coordinator._sms_inbox)
    assert "+155****0100" not in repr(coordinator._sms_inbox)
    assert "Private event body" not in caplog.text
    assert "+155****0100" not in caplog.text

    coordinator.data = second
    entry.runtime_data = GLiNetRuntimeData(client=client, coordinator=coordinator)
    diagnostics = json.dumps(await async_get_config_entry_diagnostics(hass, entry))
    assert "Private event body" not in diagnostics
    assert "+155****0100" not in diagnostics


async def test_unsupported_sms_inbox_does_not_fail_router_poll(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="router-id")
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_get_snapshot.return_value = RouterSnapshot(
        capabilities={"router", "sms"}
    )
    client.async_get_sms_messages.side_effect = GLiNetRpcError(
        -32601, "Method not found"
    )
    coordinator = GLiNetCoordinator(hass, entry, client)

    snapshot = await coordinator._async_update_data()

    assert snapshot.capabilities == {"router", "sms"}


async def test_first_poll_failure_recovers_with_a_private_baseline(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="router-id")
    entry.add_to_hass(hass)
    existing = parse_sms_messages(
        {
            "list": [
                {
                    "name": "existing-private",
                    "from": "Existing private sender",
                    "body": "Existing private body",
                    "type": 0,
                    "status": 0,
                }
            ]
        }
    )
    with_new = [
        *existing,
        *parse_sms_messages(
            {
                "list": [
                    {
                        "name": "new-private",
                        "from": "New private sender",
                        "body": "New private body",
                        "type": 0,
                        "status": 0,
                    }
                ]
            }
        ),
    ]
    client = AsyncMock()
    client.async_get_snapshot.return_value = RouterSnapshot(
        capabilities={"router", "sms"}
    )
    client.async_get_sms_messages.side_effect = [
        GLiNetRpcError(-32601, "temporary failure"),
        existing,
        with_new,
    ]
    coordinator = GLiNetCoordinator(hass, entry, client)
    events = []
    hass.bus.async_listen(EVENT_SMS_RECEIVED, events.append)

    first = await coordinator._async_update_data()
    first_capabilities = set(first.capabilities)
    second = await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert "sms_inbox" not in first_capabilities
    assert "sms_inbox" in second.capabilities
    assert events == []

    await coordinator._async_update_data()
    await hass.async_block_till_done()
    assert [event.data["message_id"] for event in events] == ["new-private"]


async def test_poll_failure_after_baseline_does_not_advance_deduplication(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="router-id")
    entry.add_to_hass(hass)
    existing = parse_sms_messages(
        {"list": [{"name": "existing", "body": "old", "type": 0, "status": 0}]}
    )
    with_new = [
        *existing,
        *parse_sms_messages(
            {"list": [{"name": "new", "body": "new", "type": 0, "status": 0}]}
        ),
    ]
    client = AsyncMock()
    client.async_get_snapshot.return_value = RouterSnapshot(
        capabilities={"router", "sms"}
    )
    client.async_get_sms_messages.side_effect = [
        existing,
        GLiNetRpcError(None, "temporary failure"),
        with_new,
    ]
    coordinator = GLiNetCoordinator(hass, entry, client)
    events = []
    hass.bus.async_listen(EVENT_SMS_RECEIVED, events.append)

    await coordinator._async_update_data()
    await coordinator._async_update_data()
    await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert [event.data["message_id"] for event in events] == ["new"]


async def test_config_entry_reload_rebaselines_existing_messages(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="router-id")
    entry.add_to_hass(hass)
    existing = parse_sms_messages(
        {"list": [{"name": "existing", "body": "old", "type": 0, "status": 0}]}
    )
    with_new = [
        *existing,
        *parse_sms_messages(
            {"list": [{"name": "new", "body": "new", "type": 0, "status": 0}]}
        ),
    ]
    events = []
    hass.bus.async_listen(EVENT_SMS_RECEIVED, events.append)

    first_client = AsyncMock()
    first_client.async_get_snapshot.return_value = RouterSnapshot(
        capabilities={"router", "sms"}
    )
    first_client.async_get_sms_messages.return_value = existing
    first_coordinator = GLiNetCoordinator(hass, entry, first_client)
    await first_coordinator._async_update_data()

    reloaded_client = AsyncMock()
    reloaded_client.async_get_snapshot.return_value = RouterSnapshot(
        capabilities={"router", "sms"}
    )
    reloaded_client.async_get_sms_messages.side_effect = [existing, with_new]
    reloaded_coordinator = GLiNetCoordinator(hass, entry, reloaded_client)
    await reloaded_coordinator._async_update_data()
    await hass.async_block_till_done()
    assert events == []

    await reloaded_coordinator._async_update_data()
    await hass.async_block_till_done()
    assert [event.data["message_id"] for event in events] == ["new"]
