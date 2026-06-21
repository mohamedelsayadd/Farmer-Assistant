import logging
from typing import Any

from core.logging import json_preview
from providers.renile_client import ReNileClient
from services.current_readings_processor import process_current_readings
from services.devices_ids_processor import process_devices_ids
from services.historical_summary_processor import process_daily_sensor_response, process_hourly_sensor_response

logger = logging.getLogger(__name__)


OPENAI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_readings",
            "description": "Get the latest farm sensor readings. Use for current, now, latest, or live readings questions.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_devices_ids",
            "description": "Get the user's available farm devices and their IDs. Required before answering historical readings questions.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_last_duration_summary",
            "description": "Get historical daily summary readings for a selected device and period. Use only after the user named a device and device_id is available from get_devices_ids context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Device ID resolved from get_devices_ids context.",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time in format YYYY-MM-DD HH:mm, resolved using today's date from the system prompt.",
                    },
                },
                "required": ["device_id", "start_time"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_specific_time_readings",
            "description": "Get historical hourly readings for a selected device on a specific previous day or time. Use only after device_id is available from get_devices_ids context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Device ID resolved from get_devices_ids context.",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Specific day start time in format YYYY-MM-DD HH:mm, resolved using today's date from the system prompt.",
                    },
                },
                "required": ["device_id", "start_time"],
                "additionalProperties": False,
            },
        },
    },
]


async def execute_current_readings_tool(jwt: str, renile_client: ReNileClient) -> dict[str, Any]:
    logger.info("tool_current_readings_started")
    raw_devices = await renile_client.get_current_readings(jwt)
    processed_readings = process_current_readings(raw_devices)
    logger.info(
        "tool_current_readings_completed raw_devices=%s processed_devices=%s result_preview=%s",
        len(raw_devices),
        len(processed_readings["devices"]),
        json_preview(processed_readings),
    )
    return processed_readings


async def execute_devices_ids_tool(jwt: str, renile_client: ReNileClient) -> dict[str, Any]:
    logger.info("tool_devices_ids_started")
    raw_devices = await renile_client.get_devices_ids(jwt)
    devices_ids = process_devices_ids(raw_devices)
    logger.info(
        "tool_devices_ids_completed raw_devices=%s processed_devices=%s result_preview=%s",
        len(raw_devices),
        len(devices_ids["devices"]),
        json_preview(devices_ids),
    )
    return devices_ids


async def execute_last_duration_summary_tool(
    jwt: str,
    renile_client: ReNileClient,
    device_id: str,
    start_time: str,
) -> dict[str, Any]:
    logger.info("tool_last_duration_summary_started device_id=%s start_time=%s data_type=month", device_id, start_time)
    raw_summary = await renile_client.get_last_duration_summary(jwt=jwt, device_id=device_id, start_time=start_time)
    daily_rows = process_daily_sensor_response(raw_summary)
    summary = {"device_id": device_id, "start_time": start_time, "data_type": "month", "daily_rows": daily_rows}
    logger.info(
        "tool_last_duration_summary_completed sensors=%s rows=%s result_preview=%s",
        len(raw_summary),
        len(daily_rows),
        json_preview(summary),
    )
    return summary


async def execute_specific_time_readings_tool(
    jwt: str,
    renile_client: ReNileClient,
    device_id: str,
    start_time: str,
) -> dict[str, Any]:
    logger.info("tool_specific_time_readings_started device_id=%s start_time=%s data_type=day", device_id, start_time)
    raw_readings = await renile_client.get_specific_time_readings(jwt=jwt, device_id=device_id, start_time=start_time)
    hourly_rows = process_hourly_sensor_response(raw_readings)
    readings = {"device_id": device_id, "start_time": start_time, "data_type": "day", "hourly_rows": hourly_rows}
    logger.info(
        "tool_specific_time_readings_completed sensors=%s rows=%s result_preview=%s",
        len(raw_readings),
        len(hourly_rows),
        json_preview(readings),
    )
    return readings


async def execute_historical_readings_tool(
    jwt: str,
    device_id: str | None = None,
    metric: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, Any]:
    logger.info(
        "tool_historical_readings_started device_id=%s metric=%s from_date=%s to_date=%s",
        device_id,
        metric,
        from_date,
        to_date,
    )
    _ = jwt
    selected_metric = metric or "temperature"
    historical_readings = {
        "device_id": device_id or "dummy-device-1",
        "metric": selected_metric,
        "from_date": from_date or "2026-06-18",
        "to_date": to_date or "2026-06-19",
        "values": [
            {"timestamp": "2026-06-18T10:00:00Z", "value": 28.1},
            {"timestamp": "2026-06-19T10:00:00Z", "value": 27.5},
        ],
        "note": "dummy data until the real ReNile API is connected",
    }
    logger.info("tool_historical_readings_completed result=%s", json_preview(historical_readings))
    return historical_readings


async def execute_tool(
    name: str,
    jwt: str,
    arguments: dict[str, Any],
    renile_client: ReNileClient,
) -> dict[str, Any]:
    logger.info("tool_dispatch_started tool_name=%s arguments=%s", name, json_preview(arguments))
    if name == "get_current_readings":
        tool_result = await execute_current_readings_tool(jwt=jwt, renile_client=renile_client)
        logger.info("tool_dispatch_completed tool_name=%s", name)
        return tool_result
    if name == "get_devices_ids":
        tool_result = await execute_devices_ids_tool(jwt=jwt, renile_client=renile_client)
        logger.info("tool_dispatch_completed tool_name=%s", name)
        return tool_result
    if name == "get_last_duration_summary":
        tool_result = await execute_last_duration_summary_tool(
            jwt=jwt,
            renile_client=renile_client,
            device_id=arguments["device_id"],
            start_time=arguments["start_time"],
        )
        logger.info("tool_dispatch_completed tool_name=%s", name)
        return tool_result
    if name == "get_specific_time_readings":
        tool_result = await execute_specific_time_readings_tool(
            jwt=jwt,
            renile_client=renile_client,
            device_id=arguments["device_id"],
            start_time=arguments["start_time"],
        )
        logger.info("tool_dispatch_completed tool_name=%s", name)
        return tool_result
    if name == "get_historical_readings":
        tool_result = await execute_historical_readings_tool(
            jwt=jwt,
            device_id=arguments.get("device_id"),
            metric=arguments.get("metric"),
            from_date=arguments.get("from_date"),
            to_date=arguments.get("to_date"),
        )
        logger.info("tool_dispatch_completed tool_name=%s", name)
        return tool_result
    logger.warning("tool_dispatch_unknown_tool tool_name=%s", name)
    raise ValueError(f"Unknown tool: {name}")
