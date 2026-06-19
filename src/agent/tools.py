import logging
from typing import Any

from core.logging import json_preview
from providers.renile_client import ReNileClient
from services.current_readings_processor import process_current_readings

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
            "name": "get_historical_readings",
            "description": "Get historical farm sensor readings. Use for old readings, yesterday, last week, trends, comparisons, or date ranges.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": ["string", "null"],
                        "description": "Optional device identifier if the farmer specified one.",
                    },
                    "metric": {
                        "type": ["string", "null"],
                        "description": "Optional reading metric, such as temperature, humidity, or soil_moisture.",
                    },
                    "from_date": {
                        "type": ["string", "null"],
                        "description": "Optional start date in ISO format when known.",
                    },
                    "to_date": {
                        "type": ["string", "null"],
                        "description": "Optional end date in ISO format when known.",
                    },
                },
                "required": [],
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
