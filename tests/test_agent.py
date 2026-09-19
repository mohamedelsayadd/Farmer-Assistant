import json
import logging
from typing import Any

import httpx
import pytest
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from agent.agent import FALLBACK_RESPONSE, MAX_TOOL_ROUNDS, FarmerAssistantAgent
from agent.tools import resolve_device_id
from conftest import FakeToolCache
from models.schemas.chat import UploadedImage

DEVICES = [{"_id": f"device-{index}", "name": f"Device {index}"} for index in range(1, 7)] + [
    {"_id": "device-7", "name": "GreenHouse Control Unit"}
]
HISTORY = [
    {"role": "user", "content": "قولي ملخص درجات الحرارة عندي اخر اسبوع"},
    {"role": "assistant", "content": "من فضلك اختر الجهاز المطلوب:\n1. Device 1\n7. GreenHouse Control Unit"},
]


class FakeChatModel(BaseChatModel):
    """Replays scripted AI messages and records every prompt it receives."""

    responses: list[AIMessage]
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeChatModel":
        return self

    def _generate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        self.calls.append(list(messages))
        message = self.responses[min(len(self.calls), len(self.responses)) - 1].model_copy(deep=True)
        return ChatResult(generations=[ChatGeneration(message=message)])


def tool_call(name: str, args: dict | None = None, call_id: str = "call-1") -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args or {}, "id": call_id}])


class FakeReNileClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.summary_device_ids: list[str] = []
        self.current_calls = 0

    async def get_devices_ids(self, jwt: str) -> list[dict]:
        assert jwt == "runtime-jwt"
        return DEVICES

    async def get_current_readings(self, jwt: str) -> dict:
        assert jwt == "runtime-jwt"
        self.current_calls += 1
        if self.fail:
            raise httpx.ConnectError("renile down")
        return {"project_name": "Farm 1", "devices": []}

    async def get_last_duration_summary(self, jwt: str, device_id: str, start_time: str) -> dict:
        assert jwt == "runtime-jwt"
        self.summary_device_ids.append(device_id)
        return {"Temperature": {"labels": ["2026-06-18T00:00:00.000Z"], "data": [{"$numberDecimal": "28.5"}]}}


class FakePlantDiseaseClient:
    async def predict(self, image_bytes: bytes, filename: str, content_type: str | None) -> dict:
        return {"is_plant": True, "is_healthy": False, "disease": "potato early blight", "source": "yolo"}


def make_agent(
    responses: list[AIMessage],
    renile_client: FakeReNileClient | None = None,
    tool_cache: FakeToolCache | None = None,
    callbacks: list | None = None,
) -> tuple[FarmerAssistantAgent, FakeChatModel, FakeReNileClient]:
    model = FakeChatModel(responses=responses)
    renile_client = renile_client or FakeReNileClient()
    agent = FarmerAssistantAgent(
        model,
        renile_client,  # type: ignore[arg-type]
        tool_cache or FakeToolCache(),  # type: ignore[arg-type]
        FakePlantDiseaseClient(),  # type: ignore[arg-type]
        callbacks=callbacks,
    )
    return agent, model, renile_client


async def run(agent: FarmerAssistantAgent, message: str = "7", history: list | None = None, image: Any = None):
    return await agent.run(
        conversation_id="conversation-1",
        jwt="runtime-jwt",
        user_message=message,
        history=HISTORY if history is None else history,
        image=image,
    )


def test_resolve_device_id_matches_exact_id_ordinal_and_name() -> None:
    assert resolve_device_id("device-2", DEVICES) == "device-2"
    assert resolve_device_id("1", DEVICES) == "device-1"
    assert resolve_device_id("greenhouse CONTROL unit", DEVICES) == "device-7"


def test_resolve_device_id_returns_none_for_blank_and_unknown() -> None:
    assert resolve_device_id("", DEVICES) is None
    assert resolve_device_id("Unknown Device", DEVICES) is None


async def test_answers_directly_without_tools() -> None:
    agent, model, _ = make_agent([AIMessage("السماد المناسب هو ...")])

    result = await run(agent, "إيه أحسن سماد للطماطم؟", history=[])

    assert result.response == "السماد المناسب هو ..."
    assert result.tool_messages == []
    assert len(model.calls) == 1


async def test_prompt_has_dated_system_message_history_and_image_marker_only_on_current_turn() -> None:
    agent, model, _ = make_agent([AIMessage("تمام")])

    await run(agent, "ايه المرض ده؟", image=UploadedImage(filename="p.jpg", content_type="image/jpeg", content=b"x"))

    prompt = model.calls[0]
    assert isinstance(prompt[0], SystemMessage)
    assert "تاريخ النهاردة:" in prompt[0].content
    assert [message.content for message in prompt[1:3]] == [item["content"] for item in HISTORY]
    assert prompt[-1].content == "ايه المرض ده؟\n\n[The user attached a plant image with this message.]"


async def test_multi_round_device_selection_follow_up() -> None:
    agent, model, renile_client = make_agent(
        [
            tool_call("get_devices_ids"),
            tool_call("get_last_duration_summary", {"device_id": "7", "start_time": "2026-06-18 00:00"}, "call-2"),
            AIMessage("ده ملخص درجات الحرارة لآخر أسبوع."),
        ]
    )

    result = await run(agent)

    assert result.response == "ده ملخص درجات الحرارة لآخر أسبوع."
    assert [len(prompt) for prompt in model.calls] == [4, 6, 8]
    assert renile_client.summary_device_ids == ["device-7"]
    assert [message.name for message in result.tool_messages] == ["get_devices_ids", "get_last_duration_summary"]
    assert json.loads(result.tool_messages[1].content)["daily_rows"] == [{"date": "2026-06-18", "Temperature": 28.5}]


async def test_historical_tool_resolves_device_name_before_api_call() -> None:
    agent, _, renile_client = make_agent(
        [
            tool_call("get_last_duration_summary", {"device_id": "GreenHouse Control Unit", "start_time": "2026-06-18 00:00"}),
            AIMessage("done"),
        ]
    )

    await run(agent)

    assert renile_client.summary_device_ids == ["device-7"]


async def test_unresolved_device_returns_device_list_instead_of_calling_renile() -> None:
    agent, _, renile_client = make_agent(
        [
            tool_call("get_last_duration_summary", {"device_id": "Mars Rover", "start_time": "2026-06-18 00:00"}),
            AIMessage("اختار الجهاز"),
        ]
    )

    result = await run(agent)

    assert renile_client.summary_device_ids == []
    assert json.loads(result.tool_messages[0].content) == DEVICES


async def test_cached_tool_result_skips_renile() -> None:
    cached_summary = {"device_id": "device-7", "start_time": "2026-06-18 00:00", "data_type": "month", "daily_rows": []}
    tool_cache = FakeToolCache(
        {
            ("get_devices_ids", "{}"): DEVICES,
            (
                "get_last_duration_summary",
                json.dumps({"device_id": "device-7", "start_time": "2026-06-18 00:00"}, sort_keys=True),
            ): cached_summary,
        }
    )
    agent, _, renile_client = make_agent(
        [
            tool_call("get_last_duration_summary", {"device_id": "device-7", "start_time": "2026-06-18 00:00"}),
            AIMessage("done"),
        ],
        tool_cache=tool_cache,
    )

    result = await run(agent)

    assert renile_client.summary_device_ids == []
    assert json.loads(result.tool_messages[0].content) == cached_summary


async def test_round_limit_returns_fallback() -> None:
    agent, model, _ = make_agent([tool_call("get_devices_ids")])

    result = await run(agent)

    assert result.response == FALLBACK_RESPONSE
    assert len(model.calls) == MAX_TOOL_ROUNDS + 1
    assert len(result.tool_messages) == MAX_TOOL_ROUNDS


async def test_failed_tool_is_reported_to_model_and_run_continues(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    agent, model, _ = make_agent(
        [tool_call("get_current_readings"), AIMessage("مش قادر أجيب القراءات دلوقتي.")],
        renile_client=FakeReNileClient(fail=True),
    )

    result = await run(agent, "القراءات؟", history=[])

    assert result.response == "مش قادر أجيب القراءات دلوقتي."
    assert result.tool_messages[0].content == "Tool failed temporarily."
    assert model.calls[1][-1].content == "Tool failed temporarily."
    assert "tool_call_failed" in caplog.text
    assert "runtime-jwt" not in caplog.text


async def test_plant_tool_without_image_fails() -> None:
    agent, _, _ = make_agent([tool_call("plant_diseases_detection"), AIMessage("ابعت صورة")])

    result = await run(agent, "شخص النبات", history=[])

    assert result.tool_messages[0].content == "Tool failed temporarily."
    assert result.tool_messages[0].status == "error"


async def test_plant_tool_with_image_returns_prediction() -> None:
    agent, _, _ = make_agent([tool_call("plant_diseases_detection"), AIMessage("النبات مصاب")])
    image = UploadedImage(filename="p.jpg", content_type="image/jpeg", content=b"secret-image-bytes")

    result = await run(agent, "شخص النبات", history=[], image=image)

    assert json.loads(result.tool_messages[0].content)["disease"] == "potato early blight"


async def test_final_answer_has_thinking_stripped() -> None:
    agent, _, _ = make_agent([AIMessage("<think>reasoning</think>الإجابة النهائية")])

    result = await run(agent, "اشرح", history=[])

    assert result.response == "الإجابة النهائية"


class RecordingCallbackHandler(AsyncCallbackHandler):
    def __init__(self) -> None:
        self.events: list[str] = []

    def _record(self, *args: Any, **kwargs: Any) -> None:
        self.events.append(repr((args, kwargs)))

    on_chain_start = on_chain_end = on_tool_start = on_tool_end = on_chat_model_start = on_llm_end = _record


async def test_jwt_and_image_bytes_never_reach_model_or_traces() -> None:
    recorder = RecordingCallbackHandler()
    agent, model, _ = make_agent(
        [tool_call("plant_diseases_detection"), tool_call("get_current_readings", call_id="call-2"), AIMessage("done")],
        callbacks=[recorder],
    )
    image = UploadedImage(filename="p.jpg", content_type="image/jpeg", content=b"secret-image-bytes")

    await run(agent, "شخص النبات", image=image)

    assert recorder.events
    traced = "\n".join(recorder.events) + repr(model.calls)
    assert "runtime-jwt" not in traced
    assert "secret-image-bytes" not in traced
