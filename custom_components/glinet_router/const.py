"""Constants for the GL.iNet Router integration."""

from typing import Final

DOMAIN: Final = "glinet_router"
MANUFACTURER: Final = "GL.iNet"
DEFAULT_NAME: Final = "GL.iNet Router"
DEFAULT_HOST: Final = "192.168.8.1"
DEFAULT_USERNAME: Final = "root"
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 15
DEFAULT_DETECTION_TIME: Final = 300
MIN_DETECTION_TIME: Final = 30
DEFAULT_MODEM_BUS: Final = "0001:01:00.0"

CONF_USE_SSL: Final = "use_ssl"
CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_TRACK_CLIENTS: Final = "track_clients"
CONF_TRACK_WIRED_CLIENTS: Final = "track_wired_clients"
CONF_IGNORE_LOCAL_MAC: Final = "ignore_local_mac"
CONF_DETECTION_TIME: Final = "detection_time"

SERVICE_SEND_SMS: Final = "send_sms"
ATTR_PHONE_NUMBER: Final = "phone_number"
ATTR_MESSAGE: Final = "message"

CONTROL_WARNING: Final = (
    "This entity changes router connectivity or configuration and may interrupt access."
)
