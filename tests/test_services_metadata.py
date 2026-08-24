from pathlib import Path

import pytest
import voluptuous as vol
import yaml

from custom_components.glinet_router import SEND_SMS_SCHEMA
from custom_components.glinet_router.const import ATTR_MESSAGE, ATTR_PHONE_NUMBER

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
        SEND_SMS_SCHEMA({ATTR_PHONE_NUMBER: "+15555550100", ATTR_MESSAGE: "x" * 161})
