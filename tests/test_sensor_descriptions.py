from homeassistant.const import EntityCategory, UnitOfInformation

from custom_components.glinet_router.sensor import SENSORS


def _description(key: str):
    return next(description for description in SENSORS if description.key == key)


def test_data_size_sensors_suggest_readable_default_units() -> None:
    for key in ("memory_free", "memory_total"):
        assert (
            _description(key).suggested_unit_of_measurement
            == UnitOfInformation.MEGABYTES
        )

    for key in ("flash_free", "flash_total", "cellular_traffic_total"):
        assert (
            _description(key).suggested_unit_of_measurement
            == UnitOfInformation.GIGABYTES
        )


def test_cellular_signal_sensors_are_disabled_diagnostics() -> None:
    for key in ("cellular_rsrp", "cellular_rsrq", "cellular_rssi", "cellular_sinr"):
        description = _description(key)
        assert description.entity_category is EntityCategory.DIAGNOSTIC
        assert description.entity_registry_enabled_default is False
