from pathlib import Path

import yaml

SERVICES_PATH = (
    Path(__file__).parents[1] / "custom_components" / "glinet_router" / "services.yaml"
)


def test_send_sms_documents_phone_number_format() -> None:
    services = yaml.safe_load(SERVICES_PATH.read_text())
    phone_number = services["send_sms"]["fields"]["phone_number"]

    assert "E.164" in phone_number["description"]
    assert "unchanged" in phone_number["description"]
    assert phone_number["example"] == "+1XXXXXXXXXX"
