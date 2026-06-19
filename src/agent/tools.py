from typing import Any


OPENAI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_readings",
            "description": "Get the latest farm sensor readings. Use for current, now, latest, or live readings questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": ["string", "null"],
                        "description": "Optional device identifier if the farmer specified one.",
                    }
                },
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


async def execute_current_readings_tool(jwt: str, device_id: str | None = None) -> dict[str, Any]:
    _ = jwt
    return {
        "device_id": device_id or "dummy-device-1",
        "temperature": 27.5,
        "humidity": 61,
        "soil_moisture": 38,
        "timestamp": "2026-06-19T10:00:00Z",
        "note": "dummy data until the real ReNile API is connected",
    }


async def execute_historical_readings_tool(
    jwt: str,
    device_id: str | None = None,
    metric: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, Any]:
    _ = jwt
    selected_metric = metric or "temperature"
    return {
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


async def execute_tool(name: str, jwt: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "get_current_readings":
        return await execute_current_readings_tool(jwt=jwt, device_id=arguments.get("device_id"))
    if name == "get_historical_readings":
        return await execute_historical_readings_tool(
            jwt=jwt,
            device_id=arguments.get("device_id"),
            metric=arguments.get("metric"),
            from_date=arguments.get("from_date"),
            to_date=arguments.get("to_date"),
        )
    raise ValueError(f"Unknown tool: {name}")
