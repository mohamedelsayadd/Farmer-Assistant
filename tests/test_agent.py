import json
import logging
from typing import Any

import httpx
import pytest
from agents import Model, ModelResponse, ModelSettings, Usage, UserError
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
from redis.exceptions import RedisError

from agent.agent import FALLBACK_RESPONSE, MAX_TOOL_ROUNDS, FarmerAssistantAgent
from agent.tools import TOOL_FAILED_MESSAGE, resolve_device_id
from conftest import FakeToolCache
from models.schemas.chat import UploadedImage

DEVICES = [{"_id": f"device-{index}", "name": f"Device {index}"} for index in range(1, 7)] + [
    {"_id": "device-7", "name": "GreenHouse Control Unit"}
]
HISTORY = [
    {"role": "user", "content": "قولي ملخص درجات الحرارة عندي اخر اسبوع"},
    {"role": "assistant", "content": "من فضلك اختر الجهاز المطلوب:\n1. Device 1\n7. GreenHouse Control Unit"},
]

ModelOutput = list[Any]


class FakeModel(Model):
    """Replays scripted model outputs and records the instructions and input of every call."""

    def __init__(self, responses: list[ModelOutput]) -> None:
        self.responses = responses
        self.calls: list[tuple[str | None, list[Any]]] = []

    async def get_response(self, system_instructions: str | None, input: Any, *args: Any, **kwargs: Any) -> ModelResponse:
        self.calls.append((system_instructions, json.loads(json.dumps(input, default=_dump_item))))
        output = self.responses[min(len(self.calls), len(self.responses)) - 1]
        return ModelResponse(output=output, usage=Usage(), response_id=None)

    def stream_response(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError


def _dump_item(item: Any) -> Any:
    return item.model_dump()


def answer(text: str) -> ModelOutput:
    return [
        ResponseOutputMessage(
            id="msg-1",
            type="message",
            role="assistant",
            status="completed",
            content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
        )
    ]


def tool_call(name: str, args: dict | None = None, call_id: str = "call-1") -> ModelOutput:
    return [
        ResponseFunctionToolCall(
            type="function_call", name=name, arguments=json.dumps(args or {}), call_id=call_id, id=f"fc-{call_id}"
        )
    ]


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
    responses: list[ModelOutput],
    renile_client: FakeReNileClient | None = None,
    tool_cache: Any = None,
) -> tuple[FarmerAssistantAgent, FakeModel, FakeReNileClient]:
    model = FakeModel(responses)
    renile_client = renile_client or FakeReNileClient()
    agent = FarmerAssistantAgent(
        model,
        ModelSettings(),
        renile_client,  # type: ignore[arg-type]
        tool_cache or FakeToolCache(),  # type: ignore[arg-type]
        FakePlantDiseaseClient(),  # type: ignore[arg-type]
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
    agent, model, _ = make_agent([answer("السماد المناسب هو ...")])

    result = await run(agent, "إيه أحسن سماد للطماطم؟", history=[])

    assert result.response == "السماد المناسب هو ..."
    assert result.tool_outputs == []
    assert len(model.calls) == 1


async def test_prompt_has_dated_system_message_history_and_image_marker_only_on_current_turn() -> None:
    agent, model, _ = make_agent([answer("تمام")])

    await run(agent, "ايه المرض ده؟", image=UploadedImage(filename="p.jpg", content_type="image/jpeg", content=b"x"))

    instructions, prompt = model.calls[0]
    assert "تاريخ النهاردة:" in instructions
    assert prompt[:2] == HISTORY
    assert prompt[-1] == {"role": "user", "content": "ايه المرض ده؟\n\n[The user attached a plant image with this message.]"}


async def test_multi_round_device_selection_follow_up() -> None:
    agent, model, renile_client = make_agent(
        [
            tool_call("get_devices_ids"),
            tool_call("get_last_duration_summary", {"device_id": "7", "start_time": "2026-06-18 00:00"}, "call-2"),
            answer("ده ملخص درجات الحرارة لآخر أسبوع."),
        ]
    )

    result = await run(agent)

    assert result.response == "ده ملخص درجات الحرارة لآخر أسبوع."
    assert [len(prompt) for _, prompt in model.calls] == [3, 5, 7]
    assert renile_client.summary_device_ids == ["device-7"]
    assert [item.name for item in result.tool_outputs] == ["get_devices_ids", "get_last_duration_summary"]
    assert json.loads(result.tool_outputs[1].output)["daily_rows"] == [{"date": "2026-06-18", "Temperature": 28.5}]


async def test_historical_tool_resolves_device_name_before_api_call() -> None:
    agent, _, renile_client = make_agent(
        [
            tool_call("get_last_duration_summary", {"device_id": "GreenHouse Control Unit", "start_time": "2026-06-18 00:00"}),
            answer("done"),
        ]
    )

    await run(agent)

    assert renile_client.summary_device_ids == ["device-7"]


async def test_unresolved_device_returns_device_list_instead_of_calling_renile() -> None:
    agent, _, renile_client = make_agent(
        [
            tool_call("get_last_duration_summary", {"device_id": "Mars Rover", "start_time": "2026-06-18 00:00"}),
            answer("اختار الجهاز"),
        ]
    )

    result = await run(agent)

    assert renile_client.summary_device_ids == []
    assert json.loads(result.tool_outputs[0].output) == DEVICES


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
            answer("done"),
        ],
        tool_cache=tool_cache,
    )

    result = await run(agent)

    assert renile_client.summary_device_ids == []
    assert json.loads(result.tool_outputs[0].output) == cached_summary


async def test_round_limit_returns_fallback() -> None:
    agent, model, _ = make_agent([tool_call("get_devices_ids")])

    result = await run(agent)

    assert result.response == FALLBACK_RESPONSE
    assert len(model.calls) == MAX_TOOL_ROUNDS + 1


async def test_failed_tool_is_reported_to_model_and_run_continues(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    agent, model, _ = make_agent(
        [tool_call("get_current_readings"), answer("مش قادر أجيب القراءات دلوقتي.")],
        renile_client=FakeReNileClient(fail=True),
    )

    result = await run(agent, "القراءات؟", history=[])

    assert result.response == "مش قادر أجيب القراءات دلوقتي."
    assert result.tool_outputs[0].output == TOOL_FAILED_MESSAGE
    assert model.calls[1][1][-1]["output"] == TOOL_FAILED_MESSAGE
    assert "tool_call_failed" in caplog.text
    assert "runtime-jwt" not in caplog.text


async def test_plant_tool_without_image_fails() -> None:
    agent, _, _ = make_agent([tool_call("plant_diseases_detection"), answer("ابعت صورة")])

    result = await run(agent, "شخص النبات", history=[])

    assert result.tool_outputs[0].output == TOOL_FAILED_MESSAGE


async def test_redis_error_in_tool_is_not_reported_to_model() -> None:
    class BrokenToolCache(FakeToolCache):
        async def get(self, **kwargs: Any) -> Any:
            raise RedisError("redis down")

    agent, _, _ = make_agent([tool_call("get_current_readings"), answer("done")], tool_cache=BrokenToolCache())

    # The SDK wraps tool exceptions in UserError (an AgentsException, which ChatService catches).
    with pytest.raises(UserError) as error:
        await run(agent, "القراءات؟", history=[])
    assert isinstance(error.value.__cause__, RedisError)


async def test_plant_tool_with_image_returns_prediction() -> None:
    agent, _, _ = make_agent([tool_call("plant_diseases_detection"), answer("النبات مصاب")])
    image = UploadedImage(filename="p.jpg", content_type="image/jpeg", content=b"secret-image-bytes")

    result = await run(agent, "شخص النبات", history=[], image=image)

    assert json.loads(result.tool_outputs[0].output)["disease"] == "potato early blight"


async def test_final_answer_has_thinking_stripped() -> None:
    agent, _, _ = make_agent([answer("<think>reasoning</think>الإجابة النهائية")])

    result = await run(agent, "اشرح", history=[])

    assert result.response == "الإجابة النهائية"


async def test_jwt_and_image_bytes_never_reach_model_or_traces(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    instrumentor = OpenAIAgentsInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    try:
        agent, model, _ = make_agent(
            [tool_call("plant_diseases_detection"), tool_call("get_current_readings", call_id="call-2"), answer("done")]
        )
        image = UploadedImage(filename="p.jpg", content_type="image/jpeg", content=b"secret-image-bytes")

        await run(agent, "شخص النبات", image=image)
    finally:
        instrumentor.uninstrument()

    spans = exporter.get_finished_spans()
    assert spans
    traced = repr([(span.name, dict(span.attributes or {})) for span in spans]) + repr(model.calls) + caplog.text
    assert "runtime-jwt" not in traced
    assert "secret-image-bytes" not in traced
