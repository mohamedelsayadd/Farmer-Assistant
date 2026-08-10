import logging

import pytest

from agent.tools import (
    OPENAI_TOOLS,
    execute_current_readings_tool,
    execute_devices_ids_tool,
    execute_last_duration_summary_tool,
    execute_specific_time_readings_tool,
)


def test_tool_schemas_do_not_expose_jwt() -> None:
    tool_payload = str(OPENAI_TOOLS).lower()

    assert "jwt" not in tool_payload
    assert "authorization" not in tool_payload


def test_current_readings_tool_has_no_agent_arguments() -> None:
    current_tool = next(tool for tool in OPENAI_TOOLS if tool["function"]["name"] == "get_current_readings")

    assert current_tool["function"]["parameters"]["properties"] == {}


def test_devices_ids_tool_has_no_agent_arguments() -> None:
    devices_tool = next(tool for tool in OPENAI_TOOLS if tool["function"]["name"] == "get_devices_ids")

    assert devices_tool["function"]["parameters"]["properties"] == {}


def test_historical_readings_tool_is_not_exposed_to_agent() -> None:
    tool_names = [tool["function"]["name"] for tool in OPENAI_TOOLS]

    assert "get_historical_readings" not in tool_names


def test_last_duration_summary_tool_schema_is_safe() -> None:
    summary_tool = next(tool for tool in OPENAI_TOOLS if tool["function"]["name"] == "get_last_duration_summary")
    parameters = summary_tool["function"]["parameters"]

    assert parameters["required"] == ["device_id", "start_time"]
    assert "data_type" not in parameters["properties"]
    assert "jwt" not in str(summary_tool).lower()


def test_specific_time_readings_tool_schema_is_safe() -> None:
    readings_tool = next(tool for tool in OPENAI_TOOLS if tool["function"]["name"] == "get_specific_time_readings")
    parameters = readings_tool["function"]["parameters"]

    assert parameters["required"] == ["device_id", "start_time"]
    assert "data_type" not in parameters["properties"]
    assert "jwt" not in str(readings_tool).lower()


BACKEND_CURRENT_READINGS = {
    "project_name": "Farm 1",
    "generated_at": "2026-08-09T12:00:00Z",
    "devices": [
        {
            "device_id": "device-1",
            "device_name": "Device 1",
            "readings": [
                {
                    "sensor": "Battery_level",
                    "value": 99,
                    "unit": "%",
                    "lower_limit": 20,
                    "upper_limit": 100,
                    "status": "normal",
                    "timestamp": "2026-06-19T10:00:00Z",
                    "age_seconds": 143,
                }
            ],
        }
    ],
}

BACKEND_DEVICES_IDS = [{"_id": "device-1", "name": "Device 1"}]


class FakeReNileClient:
    async def get_current_readings(self, jwt: str) -> dict:
        assert jwt == "runtime-jwt"
        return BACKEND_CURRENT_READINGS

    async def get_devices_ids(self, jwt: str) -> list[dict]:
        assert jwt == "runtime-jwt"
        return BACKEND_DEVICES_IDS

    async def get_last_duration_summary(self, jwt: str, device_id: str, start_time: str) -> dict:
        assert jwt == "runtime-jwt"
        assert device_id == "device-1"
        assert start_time == "2026-06-01 00:00"
        return {
            "CO2": {
                "labels": ["2026-06-01T00:00:00.000Z"],
                "data": [{"$numberDecimal": "505.94"}],
            }
        }

    async def get_specific_time_readings(self, jwt: str, device_id: str, start_time: str) -> dict:
        assert jwt == "runtime-jwt"
        assert device_id == "device-1"
        assert start_time == "2026-06-01 00:00"
        return {
            "CO2": {
                "labels": ["2026-06-01T04:00:00.000Z"],
                "data": [{"$numberDecimal": "532.55"}],
            }
        }


@pytest.mark.asyncio
async def test_current_readings_tool_returns_backend_response_unchanged() -> None:
    current_readings = await execute_current_readings_tool(
        jwt="runtime-jwt",
        renile_client=FakeReNileClient(),  # type: ignore[arg-type]
    )

    assert current_readings == BACKEND_CURRENT_READINGS


@pytest.mark.asyncio
async def test_current_readings_tool_logs_do_not_include_jwt(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    await execute_current_readings_tool(
        jwt="runtime-jwt",
        renile_client=FakeReNileClient(),  # type: ignore[arg-type]
    )

    assert "runtime-jwt" not in caplog.text
    assert "tool_current_readings_completed" in caplog.text


@pytest.mark.asyncio
async def test_devices_ids_tool_returns_backend_response_unchanged() -> None:
    devices_ids = await execute_devices_ids_tool(
        jwt="runtime-jwt",
        renile_client=FakeReNileClient(),  # type: ignore[arg-type]
    )

    assert devices_ids == BACKEND_DEVICES_IDS


@pytest.mark.asyncio
async def test_last_duration_summary_tool_returns_processed_api_response() -> None:
    summary = await execute_last_duration_summary_tool(
        jwt="runtime-jwt",
        renile_client=FakeReNileClient(),  # type: ignore[arg-type]
        device_id="device-1",
        start_time="2026-06-01 00:00",
    )

    assert summary == {
        "device_id": "device-1",
        "start_time": "2026-06-01 00:00",
        "data_type": "month",
        "daily_rows": [{"date": "2026-06-01", "CO2": 505.94}],
    }


@pytest.mark.asyncio
async def test_specific_time_readings_tool_returns_processed_api_response() -> None:
    readings = await execute_specific_time_readings_tool(
        jwt="runtime-jwt",
        renile_client=FakeReNileClient(),  # type: ignore[arg-type]
        device_id="device-1",
        start_time="2026-06-01 00:00",
    )

    assert readings == {
        "device_id": "device-1",
        "start_time": "2026-06-01 00:00",
        "data_type": "day",
        "hourly_rows": [{"timestamp": "2026-06-01T04:00:00.000Z", "CO2": 532.55}],
    }
