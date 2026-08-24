from pathlib import Path

import pytest
import voluptuous as vol
import yaml

from custom_components.glinet_router import SEND_SMS_SCHEMA, SMS_MESSAGE_ACTION_SCHEMA
from custom_components.glinet_router.const import (
    ATTR_MESSAGE,
    ATTR_MESSAGE_ID,
    ATTR_PHONE_NUMBER,
)

SERVICES_PATH = (
    Path(__file__).parents[1] / "custom_components" / "glinet_router" / "services.yaml"
)


def test_send_sms_documents_phone_number_format() -> None:
    services = yaml.safe_load(SERVICES_PATH.read_text())
    phone_number = services["send_sms"]["fields"]["phone_number"]

    assert "E.164" in phone_number["description"]
    assert "unchanged" in phone_number["description"]
    assert phone_number["example"] == "+1XXXXXXXXXX"


def test_send_sms_documents_and_enforces_160_character_limit() -> None:
    services = yaml.safe_load(SERVICES_PATH.read_text())
    message = services["send_sms"]["fields"]["message"]

    assert "160 characters" in message["description"]
    assert (
        SEND_SMS_SCHEMA({ATTR_PHONE_NUMBER: "+15555550100", ATTR_MESSAGE: "x" * 160})[
            ATTR_MESSAGE
        ]
        == "x" * 160
    )
    with pytest.raises(vol.Invalid):
        SEND_SMS_SCHEMA({ATTR_PHONE_NUMBER: "+155****0100", ATTR_MESSAGE: "x" * 161})


def test_sms_inbox_actions_document_event_message_identifier() -> None:
    services = yaml.safe_load(SERVICES_PATH.read_text())

    for action in ("mark_sms_read", "delete_sms"):
        message_id = services[action]["fields"]["message_id"]
        assert message_id["required"] is True
        assert "glinet_router_sms_received" in message_id["description"]
        assert "text" in message_id["selector"]
    assert "permanently" in services["delete_sms"]["description"].lower()


def test_sms_message_identifier_schema_is_bounded() -> None:
    assert SMS_MESSAGE_ACTION_SCHEMA({ATTR_MESSAGE_ID: "x" * 128})[ATTR_MESSAGE_ID] == (
        "x" * 128
    )
    for invalid in ("", "   ", "x" * 129):
        with pytest.raises(vol.Invalid):
            SMS_MESSAGE_ACTION_SCHEMA({ATTR_MESSAGE_ID: invalid})
