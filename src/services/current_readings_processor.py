import logging
from typing import Any

logger = logging.getLogger(__name__)


def reading_status(
    reading_value: float | int | None,
    lower_limit: float | int | None,
    upper_limit: float | int | None,
) -> str:
    if reading_value is None:
        return "unknown"
    if lower_limit is not None and reading_value < lower_limit:
        return "below_limit"
    if upper_limit is not None and reading_value > upper_limit:
        return "above_limit"
    return "normal"


def process_current_readings(devices_response: list[dict[str, Any]]) -> dict[str, Any]:
    logger.info("current_readings_processing_started raw_devices=%s", len(devices_response))
    project_name = _project_name(devices_response)
    processed_devices = [_processed_device(device) for device in devices_response]
    total_readings = sum(len(device["readings"]) for device in processed_devices)
    logger.info(
        "current_readings_processing_completed project_name=%s processed_devices=%s readings=%s",
        project_name,
        len(processed_devices),
        total_readings,
    )
    return {
        "project_name": project_name,
        "devices": processed_devices,
    }


def _project_name(devices_response: list[dict[str, Any]]) -> str | None:
    if not devices_response:
        return None
    project = devices_response[0].get("_project", {})
    if not isinstance(project, dict):
        return None
    return project.get("type")


def _processed_device(device: dict[str, Any]) -> dict[str, Any]:
    sensor_limits = _sensor_limits(device)
    return {
        "device_name": device.get("name"),
        "readings": [_processed_reading(reading, sensor_limits) for reading in device.get("lastRead", [])],
    }


def _sensor_limits(device: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sensor_limits: dict[str, dict[str, Any]] = {}
    for sensor_config in device.get("sensortypes", []):
        sensor_type = sensor_config.get("sensor_type", {})
        sensor_name = sensor_type.get("type")
        if sensor_name:
            sensor_limits[sensor_name] = {
                "unit": sensor_type.get("measurement_unit"),
                "lower_limit": sensor_config.get("lower_limit"),
                "upper_limit": sensor_config.get("upper_limit"),
            }
    return sensor_limits


def _processed_reading(reading: dict[str, Any], sensor_limits: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sensor_name = reading.get("name")
    limits = sensor_limits.get(sensor_name, {})
    lower_limit = limits.get("lower_limit")
    upper_limit = limits.get("upper_limit")
    reading_value = reading.get("reading")
    return {
        "sensor": sensor_name,
        "value": reading_value,
        "unit": limits.get("unit"),
        "lower_limit": lower_limit,
        "upper_limit": upper_limit,
        "status": reading_status(reading_value, lower_limit, upper_limit),
        "timestamp": reading.get("createdAt"),
    }
