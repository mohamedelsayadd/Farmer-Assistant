import json
from types import SimpleNamespace

import pytest

from agent.graph import FarmerAssistantAgent


def test_tool_path_routes_current_readings() -> None:
    state = {"assistant_message": _assistant_message("get_current_readings")}

    assert FarmerAssistantAgent._tool_path(state) == "current_tools"


def test_tool_path_routes_devices_ids_to_historical_path() -> None:
    state = {"assistant_message": _assistant_message("get_devices_ids")}

    assert FarmerAssistantAgent._tool_path(state) == "historical_tools"


def test_tool_path_routes_last_duration_summary_to_historical_path() -> None:
    state = {"assistant_message": _assistant_message("get_last_duration_summary")}

    assert FarmerAssistantAgent._tool_path(state) == "historical_tools"


def test_tool_path_routes_specific_time_readings_to_historical_path() -> None:
    state = {"assistant_message": _assistant_message("get_specific_time_readings")}

    assert FarmerAssistantAgent._tool_path(state) == "historical_tools"


def test_tool_path_routes_no_tool_calls_to_final() -> None:
    state = {"assistant_message": SimpleNamespace(tool_calls=[])}

    assert FarmerAssistantAgent._tool_path(state) == "final"


def _assistant_message(tool_name: str) -> SimpleNamespace:
    return SimpleNamespace(
        tool_calls=[SimpleNamespace(function=SimpleNamespace(name=tool_name))],
    )


class FakeReNileClient:
    def __init__(self) -> None:
        self.summary_device_id = None

    async def get_devices_ids(self, jwt: str) -> list[dict]:
        assert jwt == "runtime-jwt"
        return [
            {
                "name": "Local Climate monitoring system",
                "id": "device-2",
                "_project": {"type": "Farm 1"},
            }
        ]

    async def get_last_duration_summary(self, jwt: str, device_id: str, start_time: str) -> dict:
        assert jwt == "runtime-jwt"
        assert start_time == "2026-06-05 00:00"
        self.summary_device_id = device_id
        return {
            "CO2": {
                "labels": ["2026-06-05T00:00:00.000Z"],
                "data": [{"$numberDecimal": "505.94"}],
            }
        }


@pytest.mark.asyncio
async def test_historical_tool_resolves_device_name_before_api_call() -> None:
    renile_client = FakeReNileClient()
    agent = FarmerAssistantAgent(llm=SimpleNamespace(), renile_client=renile_client)  # type: ignore[arg-type]
    tool_call = SimpleNamespace(
        id="tool-1",
        function=SimpleNamespace(
            name="get_last_duration_summary",
            arguments=json.dumps(
                {
                    "device_id": "Local Climate monitoring system",
                    "start_time": "2026-06-05 00:00",
                }
            ),
        ),
    )

    tool_result, tool_context = await agent._execute_tool_call(  # noqa: SLF001
        {
            "jwt": "runtime-jwt",
            "history": [],
            "user_message": "1",
            "messages": [],
        },
        tool_call,
    )

    assert renile_client.summary_device_id == "device-2"
    assert tool_result["name"] == "get_last_duration_summary"
    assert tool_context is not None
    assert tool_context.tool_name == "get_last_duration_summary"


@pytest.mark.asyncio
async def test_historical_tool_uses_cached_device_selection_number() -> None:
    renile_client = FakeReNileClient()
    agent = FarmerAssistantAgent(llm=SimpleNamespace(), renile_client=renile_client)  # type: ignore[arg-type]
    tool_call = SimpleNamespace(
        id="tool-1",
        function=SimpleNamespace(
            name="get_last_duration_summary",
            arguments=json.dumps({"device_id": "1", "start_time": "2026-06-05 00:00"}),
        ),
    )

    await agent._execute_tool_call(  # noqa: SLF001
        {
            "jwt": "runtime-jwt",
            "history": [
                {
                    "role": "tool_context",
                    "tool_name": "get_devices_ids",
                    "content": json.dumps(
                        {
                            "devices": [
                                {
                                    "device_name": "Local Climate monitoring system",
                                    "device_id": "device-2",
                                }
                            ]
                        }
                    ),
                }
            ],
            "user_message": "1",
            "messages": [],
        },
        tool_call,
    )

    assert renile_client.summary_device_id == "device-2"
