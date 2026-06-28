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


class FakeToolCache:
    def __init__(self, cached_results: dict[tuple[str, str], dict] | None = None) -> None:
        self.cached_results = cached_results or {}
        self.stored_results: list[tuple[str, str, dict, dict]] = []

    async def get(self, conversation_id: str, tool_name: str, arguments: dict) -> dict | None:
        return self.cached_results.get((tool_name, json.dumps(arguments, sort_keys=True)))

    async def set(self, conversation_id: str, tool_name: str, arguments: dict, result: dict) -> None:
        self.stored_results.append((conversation_id, tool_name, arguments, result))
        self.cached_results[(tool_name, json.dumps(arguments, sort_keys=True))] = result


class FakeAssistantMessage:
    def __init__(self, content: str | None = None, tool_name: str | None = None, arguments: dict | None = None) -> None:
        self.content = content
        self.tool_calls = []
        if tool_name:
            self.tool_calls = [
                SimpleNamespace(
                    id=f"tool-{tool_name}",
                    function=SimpleNamespace(name=tool_name, arguments=json.dumps(arguments or {})),
                )
            ]

    def model_dump(self, exclude_none: bool = False) -> dict:
        message = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in self.tool_calls
            ]
        if exclude_none:
            return {key: value for key, value in message.items() if value is not None}
        return message


@pytest.mark.asyncio
async def test_historical_tool_resolves_device_name_before_api_call() -> None:
    renile_client = FakeReNileClient()
    tool_cache = FakeToolCache()
    agent = FarmerAssistantAgent(llm=SimpleNamespace(), renile_client=renile_client, tool_cache=tool_cache)  # type: ignore[arg-type]
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
            "conversation_id": "conversation-1",
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
    assert tool_cache.stored_results[0][1] == "get_devices_ids"
    assert tool_cache.stored_results[1][1] == "get_last_duration_summary"


@pytest.mark.asyncio
async def test_historical_tool_uses_cached_device_selection_number() -> None:
    renile_client = FakeReNileClient()
    tool_cache = FakeToolCache(
        {
            ("get_devices_ids", "{}"): {
                "devices": [
                    {
                        "device_name": "Local Climate monitoring system",
                        "device_id": "device-2",
                    }
                ]
            }
        }
    )
    agent = FarmerAssistantAgent(llm=SimpleNamespace(), renile_client=renile_client, tool_cache=tool_cache)  # type: ignore[arg-type]
    tool_call = SimpleNamespace(
        id="tool-1",
        function=SimpleNamespace(
            name="get_last_duration_summary",
            arguments=json.dumps({"device_id": "1", "start_time": "2026-06-05 00:00"}),
        ),
    )

    await agent._execute_tool_call(  # noqa: SLF001
        {
            "conversation_id": "conversation-1",
            "jwt": "runtime-jwt",
            "history": [],
            "user_message": "1",
            "messages": [],
        },
        tool_call,
    )

    assert renile_client.summary_device_id == "device-2"


@pytest.mark.asyncio
async def test_tool_call_uses_cached_result_before_api_call() -> None:
    renile_client = FakeReNileClient()
    tool_cache = FakeToolCache(
        {
            ("get_last_duration_summary", json.dumps({"device_id": "device-2", "start_time": "2026-06-05 00:00"}, sort_keys=True)): {
                "device_id": "device-2",
                "start_time": "2026-06-05 00:00",
                "data_type": "month",
                "daily_rows": [],
            },
            ("get_devices_ids", "{}"): {
                "devices": [{"device_name": "Local Climate monitoring system", "device_id": "device-2"}]
            },
        }
    )
    agent = FarmerAssistantAgent(llm=SimpleNamespace(), renile_client=renile_client, tool_cache=tool_cache)  # type: ignore[arg-type]
    tool_call = SimpleNamespace(
        id="tool-1",
        function=SimpleNamespace(
            name="get_last_duration_summary",
            arguments=json.dumps({"device_id": "device-2", "start_time": "2026-06-05 00:00"}),
        ),
    )

    tool_result, _ = await agent._execute_tool_call(  # noqa: SLF001
        {
            "conversation_id": "conversation-1",
            "jwt": "runtime-jwt",
            "history": [],
            "user_message": "1",
            "messages": [],
        },
        tool_call,
    )

    assert renile_client.summary_device_id is None
    assert json.loads(tool_result["content"])["daily_rows"] == []


class FakeStreamingLLM:
    def __init__(self) -> None:
        self.calls = 0
        self.message_counts: list[int] = []

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> FakeAssistantMessage:
        assert tools is not None
        self.calls += 1
        self.message_counts.append(len(messages))
        if self.calls == 1:
            return FakeAssistantMessage(tool_name="get_devices_ids")
        if self.calls == 2:
            return FakeAssistantMessage(
                tool_name="get_last_duration_summary",
                arguments={"device_id": "7", "start_time": "2026-06-18 00:00"},
            )
        return FakeAssistantMessage(content="ده ملخص درجات الحرارة لآخر أسبوع.")


class FakeStreamingReNileClient:
    def __init__(self) -> None:
        self.summary_device_id = None

    async def get_devices_ids(self, jwt: str) -> list[dict]:
        assert jwt == "runtime-jwt"
        return [
            {"name": f"Device {index}", "id": f"device-{index}", "_project": {"type": "Paradise Farms"}}
            for index in range(1, 7)
        ] + [
            {"name": "GreenHouse Control Unit", "id": "device-7", "_project": {"type": "Paradise Farms"}}
        ]

    async def get_last_duration_summary(self, jwt: str, device_id: str, start_time: str) -> dict:
        assert jwt == "runtime-jwt"
        assert start_time == "2026-06-18 00:00"
        self.summary_device_id = device_id
        return {
            "Temperature": {
                "labels": ["2026-06-18T00:00:00.000Z"],
                "data": [{"$numberDecimal": "28.5"}],
            }
        }


@pytest.mark.asyncio
async def test_run_stream_supports_multiple_tool_rounds_for_device_selection_follow_up() -> None:
    llm = FakeStreamingLLM()
    renile_client = FakeStreamingReNileClient()
    agent = FarmerAssistantAgent(llm=llm, renile_client=renile_client, tool_cache=FakeToolCache())  # type: ignore[arg-type]

    result = await agent.run_stream(
        conversation_id="conversation-1",
        jwt="runtime-jwt",
        user_message="7",
        history=[
            {"role": "user", "content": "قولي ملخص درجات الحرارة عندي اخر اسبوع"},
            {
                "role": "assistant",
                "content": "من فضلك اختر الجهاز المطلوب:\n1. Device 1\n7. GreenHouse Control Unit",
            },
        ],
    )

    chunks = [chunk async for chunk in result.chunks]

    assert chunks == ["ده ملخص درجات الحرارة لآخر أسبوع."]
    assert llm.calls == 3
    assert llm.message_counts == [4, 6, 8]
    assert renile_client.summary_device_id == "device-7"
    assert [context.tool_name for context in result.tool_contexts] == ["get_devices_ids", "get_last_duration_summary"]
