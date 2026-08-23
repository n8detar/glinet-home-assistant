from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

import pytest

from custom_components.glinet_router.api import (
    GLiNetApiClient,
    GLiNetRpcError,
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def json(
        self, *, content_type: str | None = "application/json"
    ) -> dict[str, Any]:
        assert content_type is None
        return self.payload


class FakeSession:
    def __init__(self, responses: Iterable[dict[str, Any]]) -> None:
        self.responses = iter(responses)
        self.requests: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        return FakeResponse(next(self.responses))


@pytest.mark.asyncio
async def test_call_authenticates_and_uses_sid(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(
        [
            {
                "result": {
                    "alg": 5,
                    "hash-method": "sha256",
                    "salt": "0123456789abcdef",
                    "nonce": "nonce",
                }
            },
            {"result": {"sid": "test-sid"}},
            {"result": {"load_average": [0.1, 0.2, 0.3]}},
        ]
    )
    monkeypatch.setattr(
        "custom_components.glinet_router.api.build_login_hash",
        lambda **kwargs: "login-hash",
    )
    client = GLiNetApiClient(
        endpoint="http://router.test/rpc",
        username="root",
        password="secret",
        session=session,
    )

    result = await client.async_call("system", "get_load")

    assert result == {"load_average": [0.1, 0.2, 0.3]}
    assert [request["json"]["method"] for request in session.requests] == [
        "challenge",
        "login",
        "call",
    ]
    call_params = session.requests[-1]["json"]["params"]
    assert call_params == ["test-sid", "system", "get_load", {}]
    assert "secret" not in repr(session.requests)


@pytest.mark.asyncio
async def test_call_reauthenticates_once_after_access_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession(
        [
            {"error": {"code": -32000, "message": "Access denied"}},
            {
                "result": {
                    "alg": 5,
                    "hash-method": "sha256",
                    "salt": "0123456789abcdef",
                    "nonce": "nonce",
                }
            },
            {"result": {"sid": "fresh-sid"}},
            {"result": {"status": 3}},
        ]
    )
    monkeypatch.setattr(
        "custom_components.glinet_router.api.build_login_hash",
        lambda **kwargs: "login-hash",
    )
    client = GLiNetApiClient(
        endpoint="http://router.test/rpc",
        username="root",
        password="secret",
        session=session,
    )
    client._sid = "expired-sid"

    result = await client.async_call("tailscale", "get_status")

    assert result == {"status": 3}
    methods = [request["json"]["method"] for request in session.requests]
    assert methods == ["call", "challenge", "login", "call"]
    assert session.requests[-1]["json"]["params"][0] == "fresh-sid"


@pytest.mark.asyncio
async def test_call_raises_non_auth_rpc_error() -> None:
    session = FakeSession([{"error": {"code": -32601, "message": "Method not found"}}])
    client = GLiNetApiClient(
        endpoint="http://router.test/rpc",
        username="root",
        password="secret",
        session=session,
    )
    client._sid = "test-sid"

    with pytest.raises(GLiNetRpcError, match="Method not found"):
        await client.async_call("modem", "missing")


@pytest.mark.asyncio
async def test_get_snapshot_discovers_modem_bus_and_sanitizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = GLiNetApiClient(
        endpoint="http://router.test/rpc",
        username="root",
        password="secret",
        session=FakeSession([]),
    )
    calls: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_call(
        service: str, method: str, params: dict[str, Any] | None = None, **_: Any
    ) -> dict[str, Any]:
        calls.append((service, method, params or {}))
        if (service, method) == ("modem", "get_info"):
            return {
                "modems": [
                    {
                        "bus": "0001:01:00.0",
                        "name": "RM520N-GL",
                        "imei": "private-imei",
                    }
                ]
            }
        if (service, method) == ("modem", "get_status"):
            return {"modems": [], "new_sms_count": 0}
        if (service, method) == ("modem", "get_cells_info"):
            return {"cells": [{"id": "private-cell", "mode": "LTE", "band": 66}]}
        return {}

    monkeypatch.setattr(client, "async_call", fake_call)

    snapshot = await client.async_get_snapshot()

    assert ("modem", "get_cells_info", {"bus": "0001:01:00.0"}) in calls
    assert snapshot.device["modem"] == "RM520N-GL"
    assert "private-imei" not in repr(snapshot)
    assert "private-cell" not in repr(snapshot)


@pytest.mark.asyncio
async def test_concurrent_calls_share_one_authentication() -> None:
    class YieldingResponse(FakeResponse):
        async def json(
            self, *, content_type: str | None = "application/json"
        ) -> dict[str, Any]:
            await asyncio.sleep(0)
            return await super().json(content_type=content_type)

    class DispatchSession:
        def __init__(self) -> None:
            self.challenge_count = 0
            self.login_count = 0

        def post(self, url: str, **kwargs: Any) -> YieldingResponse:
            payload = kwargs["json"]
            if payload["method"] == "challenge":
                self.challenge_count += 1
                result = {
                    "salt": "abcdefghijklmnop",
                    "nonce": "nonce",
                    "alg": 5,
                    "hash-method": "sha256",
                }
            elif payload["method"] == "login":
                self.login_count += 1
                result = {"sid": "shared-sid"}
            else:
                result = {"ok": True}
            return YieldingResponse({"jsonrpc": "2.0", "id": 1, "result": result})

    session = DispatchSession()
    client = GLiNetApiClient(
        endpoint="http://router/rpc",
        username="root",
        password="private-password",
        session=session,
    )

    await asyncio.gather(
        client.async_call("system", "get_info"),
        client.async_call("system", "get_status"),
        client.async_call("fan", "get_status"),
    )

    assert session.challenge_count == 1
    assert session.login_count == 1
