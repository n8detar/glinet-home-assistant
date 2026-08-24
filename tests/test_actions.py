from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.glinet_router.api import GLiNetApiClient, GLiNetRpcError
from custom_components.glinet_router.models import PRIORITY_ETHERNET_FIRST
from tests.test_api_client import FakeSession


@pytest.mark.asyncio
async def test_set_internet_priority_writes_and_verifies_complete_order() -> None:
    initial = {
        "mode": 0,
        "interfaces": [
            {"interface": "wwan", "metric": 1},
            {"interface": "modem_0001", "metric": 2},
            {"interface": "wan", "metric": 3},
            {"interface": "tethering", "metric": 4},
            {"interface": "secondwan", "metric": 5},
        ],
    }
    verified = {
        "mode": 0,
        "interfaces": [
            {"interface": "wwan", "metric": 1},
            {"interface": "wan", "metric": 2},
            {"interface": "modem_0001", "metric": 3},
            {"interface": "tethering", "metric": 4},
            {"interface": "secondwan", "metric": 5},
        ],
    }
    session = FakeSession([{"result": initial}, {"result": []}, {"result": verified}])
    client = GLiNetApiClient(
        endpoint="http://router.test/rpc",
        username="root",
        password="secret",
        session=session,
    )
    client._sid = "test-sid"

    await client.async_set_internet_priority(PRIORITY_ETHERNET_FIRST)

    set_request = session.requests[1]["json"]
    assert set_request["params"][1:3] == ["kmwan", "set_config"]
    assert set_request["params"][3] == verified


@pytest.mark.asyncio
async def test_set_internet_priority_refuses_load_balancing() -> None:
    session = FakeSession([{"result": {"mode": 1, "interfaces": []}}])
    client = GLiNetApiClient(
        endpoint="http://router.test/rpc",
        username="root",
        password="secret",
        session=session,
    )
    client._sid = "test-sid"

    with pytest.raises(GLiNetRpcError, match="failover mode"):
        await client.async_set_internet_priority(PRIORITY_ETHERNET_FIRST)

    assert len(session.requests) == 1


@pytest.mark.asyncio
async def test_send_sms_uses_minimum_verified_payload() -> None:
    session = FakeSession([{"result": []}])
    client = GLiNetApiClient(
        endpoint="http://router.test/rpc",
        username="root",
        password="secret",
        session=session,
    )
    client._sid = "test-sid"

    await client.async_send_sms(
        bus="0001:01:00.0", phone_number="+15551234567", message="hello"
    )

    params: list[Any] = session.requests[0]["json"]["params"]
    assert params[1:3] == ["modem", "send_sms"]
    assert params[3] == {
        "bus": "0001:01:00.0",
        "phone_number": "+15551234567",
        "body": "hello",
        "timeout": 0,
    }
    assert "sender" not in params[3]


@pytest.mark.asyncio
async def test_get_sms_messages_normalizes_inbox_response() -> None:
    session = FakeSession(
        [
            {
                "result": {
                    "list": [
                        {
                            "name": "sms-inbound-1",
                            "phone_number": "+155****0100",
                            "body": "Private test body",
                            "type": 0,
                            "status": 0,
                        }
                    ]
                }
            }
        ]
    )
    client = GLiNetApiClient(
        endpoint="http://router.test/rpc",
        username="root",
        password="secret",
        session=session,
    )
    client._sid = "test-sid"

    messages = await client.async_get_sms_messages()

    assert [message.message_id for message in messages] == ["sms-inbound-1"]
    assert session.requests[0]["json"]["params"][1:] == [
        "modem",
        "get_sms_list",
        {},
    ]


@pytest.mark.asyncio
async def test_get_sms_messages_rejects_malformed_list() -> None:
    session = FakeSession([{"result": {"unexpected": []}}])
    client = GLiNetApiClient(
        endpoint="http://router.test/rpc",
        username="root",
        password="secret",
        session=session,
    )
    client._sid = "test-sid"

    with pytest.raises(GLiNetRpcError, match="Malformed SMS inbox response"):
        await client.async_get_sms_messages()


@pytest.mark.asyncio
async def test_mark_sms_read_uses_verified_payload() -> None:
    session = FakeSession([{"result": []}])
    client = GLiNetApiClient(
        endpoint="http://router.test/rpc",
        username="root",
        password="secret",
        session=session,
    )
    client._sid = "test-sid"

    await client.async_mark_sms_read(message_id="sms-inbound-1")

    assert session.requests[0]["json"]["params"][1:] == [
        "modem",
        "set_sms",
        {"name": "sms-inbound-1", "status": 1},
    ]


@pytest.mark.asyncio
async def test_delete_sms_uses_single_message_scope() -> None:
    session = FakeSession([{"result": []}])
    client = GLiNetApiClient(
        endpoint="http://router.test/rpc",
        username="root",
        password="secret",
        session=session,
    )
    client._sid = "test-sid"

    await client.async_delete_sms(message_id="sms-inbound-1")

    assert session.requests[0]["json"]["params"][1:] == [
        "modem",
        "remove_sms",
        {"name": "sms-inbound-1", "scope": 10},
    ]


@pytest.mark.asyncio
async def test_mark_all_sms_read_updates_only_unread_inbound_messages() -> None:
    session = FakeSession(
        [
            {
                "result": {
                    "list": [
                        {"name": "unread", "type": 0, "status": 0},
                        {"name": "already-read", "type": 0, "status": 1},
                        {"name": "sent", "type": 1, "status": 2},
                    ]
                }
            },
            {"result": []},
        ]
    )
    client = GLiNetApiClient(
        endpoint="http://router.test/rpc",
        username="root",
        password="secret",
        session=session,
    )
    client._sid = "test-sid"

    await client.async_mark_all_sms_read()

    calls = [request["json"]["params"][1:] for request in session.requests]
    assert calls == [
        ["modem", "get_sms_list", {}],
        ["modem", "set_sms", {"name": "unread", "status": 1}],
    ]


@pytest.mark.asyncio
async def test_delete_all_read_sms_uses_read_scope() -> None:
    session = FakeSession([{"result": []}])
    client = GLiNetApiClient(
        endpoint="http://router.test/rpc",
        username="root",
        password="secret",
        session=session,
    )
    client._sid = "test-sid"

    await client.async_delete_all_read_sms()

    assert session.requests[0]["json"]["params"][1:] == [
        "modem",
        "remove_sms",
        {"scope": 1},
    ]


@pytest.mark.asyncio
async def test_reboot_router_uses_system_reboot() -> None:
    session = FakeSession([{"result": []}])
    client = GLiNetApiClient(
        endpoint="http://router.test/rpc",
        username="root",
        password="secret",
        session=session,
    )
    client._sid = "test-sid"

    await client.async_reboot_router()

    params: list[Any] = session.requests[0]["json"]["params"]
    assert params[1:3] == ["system", "reboot"]
    assert params[3] == {}


@pytest.mark.asyncio
async def test_reconnect_cellular_disconnects_then_connects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession([{"result": []}, {"result": []}])
    client = GLiNetApiClient(
        endpoint="http://router.test/rpc",
        username="root",
        password="secret",
        session=session,
    )
    client._sid = "test-sid"
    sleep = AsyncMock()
    monkeypatch.setattr("custom_components.glinet_router.api.asyncio.sleep", sleep)

    await client.async_reconnect_cellular(bus="0001:01:00.0")

    calls = [request["json"]["params"] for request in session.requests]
    assert [params[1:3] for params in calls] == [
        ["modem", "disconnect"],
        ["modem", "set_connect"],
    ]
    assert all(params[3] == {"bus": "0001:01:00.0"} for params in calls)
    sleep.assert_awaited_once_with(2)
