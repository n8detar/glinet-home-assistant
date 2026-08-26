"""Asynchronous GL.iNet JSON-RPC client."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Final, Protocol

from passlib.hash import md5_crypt, sha256_crypt, sha512_crypt

from .models import (
    RouterSnapshot,
    SmsMessage,
    build_failover_payload,
    build_snapshot,
    parse_sms_messages,
)

_SUPPORTED_HASHES: Final = {"md5", "sha256", "sha512"}


class GLiNetError(Exception):
    """Base GL.iNet API error."""


class GLiNetUnsupportedAlgorithm(GLiNetError):
    """The router requested an unsupported authentication algorithm."""


class GLiNetAuthenticationError(GLiNetError):
    """Authentication with the router failed."""


class GLiNetRpcError(GLiNetError):
    """The router returned a JSON-RPC error."""

    def __init__(self, code: int | None, message: str) -> None:
        super().__init__(f"GL.iNet RPC error {code}: {message}")
        self.code = code
        self.message = message


class _Response(Protocol):
    """Subset of an aiohttp response used by the client."""

    def raise_for_status(self) -> None: ...

    async def json(self, *, content_type: str | None = None) -> dict[str, Any]: ...


class _ResponseContext(Protocol):
    """Async context manager returned by aiohttp post."""

    async def __aenter__(self) -> _Response: ...

    async def __aexit__(self, *args: object) -> None: ...


class _Session(Protocol):
    """Subset of aiohttp ClientSession used by the client."""

    def post(self, url: str, **kwargs: Any) -> _ResponseContext: ...


class GLiNetApiClient:
    """Asynchronous JSON-RPC client for GL.iNet firmware 4.x."""

    def __init__(
        self,
        *,
        endpoint: str,
        username: str,
        password: str,
        session: _Session,
        timeout: float = 10.0,
    ) -> None:
        self._endpoint = endpoint
        self._username = username
        self._password = password
        self._session = session
        self._timeout = timeout
        self._sid: str | None = None
        self._request_id = 0
        self._auth_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    @property
    def endpoint(self) -> str:
        """Return the configured RPC endpoint."""
        return self._endpoint

    async def _async_request(
        self, method: str, params: Any
    ) -> dict[str, Any] | list[Any]:
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        async with self._session.post(
            self._endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self._timeout,
        ) as response:
            response.raise_for_status()
            result = await response.json(content_type=None)
        if error := result.get("error"):
            raise GLiNetRpcError(
                error.get("code"), error.get("message", "Unknown error")
            )
        rpc_result = result.get("result")
        if not isinstance(rpc_result, dict) and not isinstance(rpc_result, list):
            raise GLiNetRpcError(None, "Malformed response")
        return rpc_result

    async def async_authenticate(self) -> None:
        """Authenticate once when concurrent calls need a session."""
        async with self._auth_lock:
            if self._sid is None:
                await self._async_authenticate_unlocked()

    async def _async_authenticate_unlocked(self) -> None:
        """Negotiate the advertised challenge while holding the auth lock."""
        challenge = await self._async_request("challenge", {"username": self._username})
        if not isinstance(challenge, dict):
            raise GLiNetAuthenticationError("Malformed authentication challenge")
        try:
            login_hash = build_login_hash(
                username=self._username,
                password=self._password,
                salt=str(challenge["salt"]),
                nonce=str(challenge["nonce"]),
                algorithm=int(challenge.get("alg", 1)),
                hash_method=str(challenge.get("hash-method", "md5")),
            )
        except (KeyError, TypeError, ValueError) as err:
            raise GLiNetAuthenticationError(
                "Malformed authentication challenge"
            ) from err
        try:
            result = await self._async_request(
                "login", {"username": self._username, "hash": login_hash}
            )
        except GLiNetRpcError as err:
            raise GLiNetAuthenticationError("Router rejected credentials") from err
        sid = result.get("sid") if isinstance(result, dict) else None
        if not isinstance(sid, str) or not sid:
            raise GLiNetAuthenticationError("Login response did not contain a SID")
        self._sid = sid

    async def _async_refresh_authentication(self, expired_sid: str | None) -> None:
        """Replace an expired SID once, coalescing concurrent refreshes."""
        async with self._auth_lock:
            if self._sid is not None and self._sid != expired_sid:
                return
            self._sid = None
            await self._async_authenticate_unlocked()

    async def async_get_system_info(self) -> dict[str, Any]:
        """Return system identity for config-flow validation only."""
        result = await self.async_call("system", "get_info")
        if not isinstance(result, dict):
            raise GLiNetRpcError(None, "Malformed system information")
        return result

    @staticmethod
    def _is_auth_error(error: GLiNetRpcError) -> bool:
        message = error.message.lower()
        return any(
            marker in message
            for marker in ("access denied", "unauthorized", "invalid sid", "no sid")
        )

    async def async_call(
        self,
        service: str,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        _retry_auth: bool = True,
    ) -> dict[str, Any] | list[Any]:
        """Call an authenticated service method, refreshing an expired SID once."""
        if self._sid is None:
            await self.async_authenticate()
        sid = self._sid
        try:
            return await self._async_request(
                "call", [sid, service, method, params or {}]
            )
        except GLiNetRpcError as err:
            if _retry_auth and self._is_auth_error(err):
                await self._async_refresh_authentication(sid)
                return await self.async_call(service, method, params, _retry_auth=False)
            if self._is_auth_error(err):
                raise GLiNetAuthenticationError("Authentication failed") from err
            raise

    async def _async_optional_call(
        self, service: str, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[Any]:
        """Call an optional firmware method and ignore only method-not-found."""
        try:
            return await self.async_call(service, method, params)
        except GLiNetRpcError as err:
            if self._is_auth_error(err):
                raise
            return {}

    async def async_get_snapshot(
        self, *, include_clients: bool = True
    ) -> RouterSnapshot:
        """Fetch passive endpoints and immediately discard raw private fields."""
        core_specs = (
            ("system_info", "system", "get_info"),
            ("system_status", "system", "get_status"),
        )
        optional_specs = (
            ("fan_status", "fan", "get_status"),
            ("led_config", "led", "get_config"),
            ("kmwan_config", "kmwan", "get_config"),
            ("kmwan_status", "kmwan", "get_status"),
            ("kmwan_sensitivity", "kmwan", "get_sensitivity"),
            ("modem_info", "modem", "get_info"),
            ("modem_status", "modem", "get_status"),
            ("tailscale_config", "tailscale", "get_config"),
            ("tailscale_status", "tailscale", "get_status"),
            ("vpn_tunnel", "vpn-client", "get_tunnel"),
            ("adguard_config", "adguardhome", "get_config"),
            ("firewall_rules", "firewall", "get_rule_list"),
            ("port_forwards", "firewall", "get_port_forward_list"),
            ("ddns_config", "ddns", "get_config"),
            ("ddns_status", "ddns", "get_status"),
            ("zerotier_config", "zerotier", "get_config"),
            ("zerotier_status", "zerotier", "get_status"),
        )
        if include_clients:
            optional_specs += (("clients", "clients", "get_list"),)
        core_results = await asyncio.gather(
            *(self.async_call(service, method) for _, service, method in core_specs)
        )
        optional_results = await asyncio.gather(
            *(
                self._async_optional_call(service, method)
                for _, service, method in optional_specs
            )
        )
        responses = dict(
            zip((spec[0] for spec in core_specs), core_results, strict=True)
        )
        responses.update(
            zip((spec[0] for spec in optional_specs), optional_results, strict=True)
        )

        modem_info = responses.get("modem_info")
        modem_bus: str | None = None
        if isinstance(modem_info, dict):
            modems = modem_info.get("modems")
            if isinstance(modems, list) and modems and isinstance(modems[0], dict):
                bus = modems[0].get("bus")
                if isinstance(bus, str):
                    modem_bus = bus
        if modem_bus:
            responses["cells_info"] = await self._async_optional_call(
                "modem", "get_cells_info", {"bus": modem_bus}
            )

        return build_snapshot(responses)

    async def _async_serialized_call(
        self, service: str, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[Any]:
        """Serialize a state-changing RPC call."""
        async with self._write_lock:
            return await self.async_call(service, method, params)

    async def async_set_internet_priority(self, option: str) -> None:
        """Set and verify one of the two supported failover orders."""
        async with self._write_lock:
            current = await self.async_call("kmwan", "get_config")
            if not isinstance(current, dict) or current.get("mode") != 0:
                raise GLiNetRpcError(None, "Internet priority requires failover mode")
            payload = build_failover_payload(option)
            await self.async_call("kmwan", "set_config", payload)
            verified = await self.async_call("kmwan", "get_config")
            if not isinstance(verified, dict):
                raise GLiNetRpcError(None, "Could not verify internet priority")
            actual = {
                "mode": verified.get("mode"),
                "interfaces": [
                    {
                        "interface": item.get("interface"),
                        "metric": item.get("metric"),
                    }
                    for item in verified.get("interfaces", [])
                    if isinstance(item, dict)
                ],
            }
            if actual != payload:
                raise GLiNetRpcError(None, "Router did not apply internet priority")

    async def async_set_led(self, enabled: bool) -> None:
        """Set and verify the status-indicator state."""
        async with self._write_lock:
            current = await self.async_call("led", "get_config")
            if not isinstance(current, dict) or not isinstance(
                current.get("led_enable"), bool
            ):
                raise GLiNetRpcError(None, "Malformed LED configuration")
            await self.async_call("led", "set_config", {"led_enable": enabled})
            verified = await self.async_call("led", "get_config")
            if (
                not isinstance(verified, dict)
                or verified.get("led_enable") is not enabled
            ):
                raise GLiNetRpcError(None, "Router did not apply LED state")

    async def async_send_sms(
        self, *, bus: str, phone_number: str, message: str
    ) -> None:
        """Send an SMS without retaining or logging destination or body."""
        await self._async_serialized_call(
            "modem",
            "send_sms",
            {
                "bus": bus,
                "phone_number": phone_number,
                "body": message,
                "timeout": 0,
            },
        )

    async def async_get_sms_messages(self) -> list[SmsMessage]:
        """Fetch and normalize the SMS inbox for transient processing."""
        response = await self.async_call("modem", "get_sms_list")
        if not isinstance(response, dict) or not isinstance(response.get("list"), list):
            raise GLiNetRpcError(None, "Malformed SMS inbox response")
        return parse_sms_messages(response)

    async def async_mark_sms_read(self, *, message_id: str) -> None:
        """Mark one SMS inbox message read."""
        await self._async_serialized_call(
            "modem", "set_sms", {"name": message_id, "status": 1}
        )

    async def async_delete_sms(self, *, message_id: str) -> None:
        """Delete one named SMS inbox message."""
        await self._async_serialized_call(
            "modem", "remove_sms", {"name": message_id, "scope": 10}
        )

    async def async_mark_all_sms_read(self) -> None:
        """Mark every currently unread inbound SMS message read."""
        async with self._write_lock:
            messages = await self.async_get_sms_messages()
            for message in messages:
                if message.message_type == 0 and message.status == 0:
                    await self.async_call(
                        "modem",
                        "set_sms",
                        {"name": message.message_id, "status": 1},
                    )

    async def async_delete_all_read_sms(self) -> None:
        """Delete all SMS messages the router currently marks read."""
        await self._async_serialized_call("modem", "remove_sms", {"scope": 1})

    async def async_set_tailscale(self, key: str, enabled: bool) -> None:
        """Change one allowlisted Tailscale setting while preserving the others."""
        if key not in {"enabled", "lan_enabled", "wan_enabled"}:
            raise ValueError(f"Unsupported Tailscale setting: {key}")
        async with self._write_lock:
            current = await self.async_call("tailscale", "get_config")
            if not isinstance(current, dict):
                raise GLiNetRpcError(None, "Malformed Tailscale configuration")
            desired_enabled = (
                enabled if key == "enabled" else bool(current.get("enabled"))
            )
            if not desired_enabled:
                payload: dict[str, Any] = {"enabled": False}
            else:
                payload = {
                    "enabled": True,
                    "lan_enabled": (
                        enabled
                        if key == "lan_enabled"
                        else bool(current.get("lan_enabled"))
                    ),
                    "wan_enabled": (
                        enabled
                        if key == "wan_enabled"
                        else bool(current.get("wan_enabled"))
                    ),
                    "exit_node_ip": current.get("exit_node_ip", ""),
                }
            await self.async_call("tailscale", "set_config", payload)

    async def async_set_adguard(self, key: str, enabled: bool) -> None:
        """Change AdGuard Home enablement using the frontend's payload shape."""
        if key not in {"enabled", "dns_enabled"}:
            raise ValueError(f"Unsupported AdGuard setting: {key}")
        async with self._write_lock:
            current = await self.async_call("adguardhome", "get_config")
            if not isinstance(current, dict):
                raise GLiNetRpcError(None, "Malformed AdGuard Home configuration")
            if key == "enabled" and not enabled:
                payload = {"enabled": False}
            else:
                payload = {
                    "enabled": True,
                    "dns_enabled": (
                        enabled
                        if key == "dns_enabled"
                        else bool(current.get("dns_enabled"))
                    ),
                }
            await self.async_call("adguardhome", "set_config", payload)

    async def async_reboot_router(self) -> None:
        """Request a router reboot."""
        await self._async_serialized_call("system", "reboot")

    async def async_reconnect_cellular(self, *, bus: str) -> None:
        """Disconnect and reconnect the cellular modem as one serialized action."""
        async with self._write_lock:
            await self.async_call("modem", "disconnect", {"bus": bus})
            await asyncio.sleep(2)
            await self.async_call("modem", "set_connect", {"bus": bus})


def _password_crypt(password: str, salt: str, algorithm: int) -> str:
    """Create the Unix crypt password requested by the challenge."""
    if algorithm == 1:
        return md5_crypt.using(salt=salt).hash(password)
    if algorithm == 5:
        return sha256_crypt.using(salt=salt, rounds=5000).hash(password)
    if algorithm == 6:
        return sha512_crypt.using(salt=salt, rounds=5000).hash(password)
    raise GLiNetUnsupportedAlgorithm(f"Unsupported crypt algorithm: {algorithm}")


def build_login_hash(
    *,
    username: str,
    password: str,
    salt: str,
    nonce: str,
    algorithm: int,
    hash_method: str,
) -> str:
    """Build a negotiated GL.iNet firmware 4.x login hash."""
    cipher_password = _password_crypt(password, salt, algorithm)
    normalized_hash = hash_method.lower().replace("-", "")
    if normalized_hash not in _SUPPORTED_HASHES:
        raise GLiNetUnsupportedAlgorithm(
            f"Unsupported challenge hash method: {hash_method}"
        )
    digest = getattr(hashlib, normalized_hash)
    material = f"{username}:{cipher_password}:{nonce}".encode()
    return digest(material).hexdigest()
