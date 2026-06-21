import logging
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)


def process_daily_sensor_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    logger.info("historical_summary_processing_started sensors=%s", len(response))
    daily_rows: dict[str, dict[str, Any]] = {}
    for sensor_name, sensor_payload in response.items():
        labels = sensor_payload.get("labels", [])
        sensor_values = sensor_payload.get("data", [])
        for label, sensor_value in zip(labels, sensor_values):
            date = label.split("T")[0]
            daily_rows.setdefault(date, {"date": date})[sensor_name] = parse_decimal_value(sensor_value)

    rows = list(daily_rows.values())
    logger.info("historical_summary_processing_completed rows=%s", len(rows))
    return rows


def process_hourly_sensor_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    logger.info("historical_hourly_processing_started sensors=%s", len(response))
    hourly_rows: dict[str, dict[str, Any]] = {}
    for sensor_name, sensor_payload in response.items():
        labels = sensor_payload.get("labels", [])
        sensor_values = sensor_payload.get("data", [])
        for timestamp, sensor_value in zip(labels, sensor_values):
            hourly_rows.setdefault(timestamp, {"timestamp": timestamp})[sensor_name] = parse_decimal_value(sensor_value)

    rows = list(hourly_rows.values())
    logger.info("historical_hourly_processing_completed rows=%s", len(rows))
    return rows


def parse_decimal_value(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, dict) and "$numberDecimal" in value:
        return _decimal_to_float(value["$numberDecimal"])
    if isinstance(value, (int, float)):
        return value
    return None


def _decimal_to_float(value: Any) -> float | None:
    try:
        return float(Decimal(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
