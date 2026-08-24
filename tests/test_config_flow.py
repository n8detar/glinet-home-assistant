from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.glinet_router.const import (
    CONF_DETECTION_TIME,
    CONF_IGNORE_LOCAL_MAC,
    CONF_SCAN_INTERVAL,
    CONF_TRACK_CLIENTS,
    CONF_TRACK_WIRED_CLIENTS,
    CONF_USE_SSL,
    DOMAIN,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def test_user_flow_creates_entry(hass, monkeypatch: pytest.MonkeyPatch) -> None:
    validate = AsyncMock(
        return_value={"title": "GL-X3000", "unique_id": "hashed-router-id"}
    )
    monkeypatch.setattr(
        "custom_components.glinet_router.config_flow.async_validate_input", validate
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    user_input = {
        CONF_HOST: "192.168.8.1",
        CONF_USERNAME: "root",
        CONF_PASSWORD: "private-password",
        CONF_USE_SSL: False,
        CONF_VERIFY_SSL: False,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=user_input
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "GL-X3000"
    assert result["data"] == user_input
    assert result["result"].unique_id == "hashed-router-id"


async def test_duplicate_router_is_rejected(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
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
    monkeypatch.setattr(
        "custom_components.glinet_router.config_flow.async_validate_input",
        AsyncMock(return_value={"title": "GL-X3000", "unique_id": "hashed-router-id"}),
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={
            CONF_HOST: "router.test",
            CONF_USERNAME: "root",
            CONF_PASSWORD: "private-password",
            CONF_USE_SSL: False,
            CONF_VERIFY_SSL: False,
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_saves_unifi_style_client_tracking_options(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="hashed-router-id",
        data={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    options = {
        CONF_SCAN_INTERVAL: 30,
        CONF_TRACK_CLIENTS: True,
        CONF_TRACK_WIRED_CLIENTS: True,
        CONF_IGNORE_LOCAL_MAC: False,
        CONF_DETECTION_TIME: 300,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input=options
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == options
