from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.glinet_router.api import GLiNetApiClient
from custom_components.glinet_router.const import CONF_USE_SSL, DOMAIN, SERVICE_SEND_SMS
from custom_components.glinet_router.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.glinet_router.models import RouterClient, RouterSnapshot

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
    ):
        entity_id = registry.async_get_entity_id("button", DOMAIN, unique_id)
        assert entity_id is not None
        assert (
            registry.async_get(entity_id).disabled_by
            is er.RegistryEntryDisabler.INTEGRATION
        )


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
