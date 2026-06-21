import logging

import pytest

from agent.tools import OPENAI_TOOLS, execute_current_readings_tool, execute_devices_ids_tool


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


class FakeReNileClient:
    async def get_current_readings(self, jwt: str) -> list[dict]:
        assert jwt == "runtime-jwt"
        return [
            {
                "name": "Device 1",
                "_project": {"type": "Farm 1"},
                "sensortypes": [],
                "lastRead": [{"name": "Battery_level", "reading": 99, "createdAt": "2026-06-19T10:00:00Z"}],
            }
        ]

    async def get_devices_ids(self, jwt: str) -> list[dict]:
        assert jwt == "runtime-jwt"
        return [
            {
                "name": "Device 1",
                "id": "device-1",
                "_project": {"type": "Farm 1"},
            }
        ]


@pytest.mark.asyncio
async def test_current_readings_tool_returns_processed_api_response() -> None:
    processed_readings = await execute_current_readings_tool(
        jwt="runtime-jwt",
        renile_client=FakeReNileClient(),  # type: ignore[arg-type]
    )

    assert processed_readings["project_name"] == "Farm 1"
    assert processed_readings["devices"][0]["device_name"] == "Device 1"
    assert processed_readings["devices"][0]["readings"][0]["sensor"] == "Battery_level"


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
async def test_devices_ids_tool_returns_processed_api_response() -> None:
    devices_ids = await execute_devices_ids_tool(
        jwt="runtime-jwt",
        renile_client=FakeReNileClient(),  # type: ignore[arg-type]
    )

    assert devices_ids == {
        "project_name": "Farm 1",
        "devices": [{"device_name": "Device 1", "device_id": "device-1"}],
    }
