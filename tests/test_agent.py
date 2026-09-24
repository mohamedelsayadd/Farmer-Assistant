import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from agents import Model, ModelResponse, RunConfig, Usage
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
from redis.exceptions import RedisError

from agent.agent import FALLBACK_RESPONSE, MAX_TOOL_ROUNDS, farmer_agent, support_agent
from agent.tools import TOOL_FAILED_MESSAGE, resolve_device_id
from conftest import FakeToolCache
from models.schemas.chat import ChatRequest, ChatResponse, UploadedImage
from services.chat_service import ChatService

DEVICES = [{"_id": f"device-{index}", "name": f"Device {index}"} for index in range(1, 7)] + [
    {"_id": "device-7", "name": "GreenHouse Control Unit"}
]
DEVICES_STATUS = [
    {
        "_id": "device-7",
        "name": "GreenHouse Control Unit",
        "last_reading_time": "2026-09-01T10:00:00+00:00",
        "readings": {"Temperature": 30.1},
        "connection_type": "4G",
        "renewal_type": "manual",
        "renewal_date": "2026-09-01",
    }
]
HANDOFF = "transfer_to_customer_support_agent"
HANDBACK = "transfer_to_farmer_assistant"
SUPPORT_AGENT = "Customer Support Agent"
FARMER_AGENT = "Farmer Assistant"
SUPPORT_MARKER = "ReNile Customer Support"
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
        self.status_calls = 0

    async def get_devices_ids(self, jwt: str) -> list[dict]:
        assert jwt == "runtime-jwt"
        return DEVICES

    async def get_current_readings(self, jwt: str) -> dict:
        assert jwt == "runtime-jwt"
        self.current_calls += 1
        if self.fail:
            raise httpx.ConnectError("renile down")
        return {"project_name": "Farm 1", "devices": []}

    async def get_devices_status(self, jwt: str) -> list[dict]:
        assert jwt == "runtime-jwt"
        self.status_calls += 1
        return DEVICES_STATUS

    async def get_last_duration_summary(self, jwt: str, device_id: str, start_time: str) -> dict:
        assert jwt == "runtime-jwt"
        self.summary_device_ids.append(device_id)
        return {"Temperature": {"labels": ["2026-06-18T00:00:00.000Z"], "data": [{"$numberDecimal": "28.5"}]}}


class FakePlantDiseaseClient:
    async def predict(self, image_bytes: bytes, filename: str, content_type: str | None) -> dict:
        return {"is_plant": True, "is_healthy": False, "disease": "potato early blight", "source": "yolo"}


class FakeMemory:
    def __init__(self, history: list[dict]) -> None:
        self.history = history
        self.events: list[tuple[str, str]] = []
        self.agents: list[str | None] = []

    async def load(self, conversation_id: str) -> list[dict]:
        assert conversation_id == "conversation-1"
        return self.history

    async def append(self, conversation_id: str, role: str, content: str, agent: str | None = None) -> None:
        self.events.append((role, content))
        if role == "assistant":
            self.agents.append(agent)


@dataclass
class ToolOutput:
    name: str
    output: str


@dataclass
class Harness:
    model: FakeModel
    renile_client: FakeReNileClient
    tool_cache: Any
    memory: FakeMemory = field(default_factory=lambda: FakeMemory(HISTORY))


@dataclass
class Result:
    chat: ChatResponse
    tool_outputs: list[ToolOutput]

    @property
    def response(self) -> str:
        return self.chat.message


def make_agent(
    responses: list[ModelOutput],
    renile_client: FakeReNileClient | None = None,
    tool_cache: Any = None,
) -> tuple[Harness, FakeModel, FakeReNileClient]:
    harness = Harness(FakeModel(responses), renile_client or FakeReNileClient(), tool_cache or FakeToolCache())
    return harness, harness.model, harness.renile_client


async def run(harness: Harness, message: str = "7", history: list | None = None, image: Any = None) -> Result:
    harness.memory = FakeMemory(HISTORY if history is None else history)
    service = ChatService(
        memory=harness.memory,  # type: ignore[arg-type]
        renile_client=harness.renile_client,  # type: ignore[arg-type]
        tool_cache=harness.tool_cache,
        plant_disease_client=FakePlantDiseaseClient(),  # type: ignore[arg-type]
        run_config=RunConfig(model=harness.model),
    )
    chat = await service.chat(
        ChatRequest(jwt="runtime-jwt", conversation_id="conversation-1", message=message, image=image)
    )
    return Result(chat=chat, tool_outputs=tool_outputs(harness.model))


def tool_outputs(model: FakeModel) -> list[ToolOutput]:
    """Tool results as the model saw them on its last call, paired with their tool names."""
    if not model.calls:
        return []
    items = model.calls[-1][1]
    names = {item["call_id"]: item["name"] for item in items if item.get("type") == "function_call"}
    return [
        ToolOutput(name=names[item["call_id"]], output=item["output"])
        for item in items
        if item.get("type") == "function_call_output"
    ]


def test_resolve_device_id_matches_exact_id_ordinal_and_name() -> None:
    assert resolve_device_id("device-2", DEVICES) == "device-2"
    assert resolve_device_id("1", DEVICES) == "device-1"
    assert resolve_device_id("greenhouse CONTROL unit", DEVICES) == "device-7"


def test_resolve_device_id_returns_none_for_blank_and_unknown() -> None:
    assert resolve_device_id("", DEVICES) is None
    assert resolve_device_id("Unknown Device", DEVICES) is None


async def test_answers_directly_without_tools_and_saves_only_the_turn() -> None:
    agent, model, _ = make_agent([answer("السماد المناسب هو ...")])

    result = await run(agent, "إيه أحسن سماد للطماطم؟", history=[])

    assert result.response == "السماد المناسب هو ..."
    assert result.tool_outputs == []
    assert len(model.calls) == 1
    assert agent.memory.events == [("user", "إيه أحسن سماد للطماطم؟"), ("assistant", "السماد المناسب هو ...")]


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
    # Tool results are never written into prompt memory.
    assert agent.memory.events == [("user", "7"), ("assistant", "ده ملخص درجات الحرارة لآخر أسبوع.")]
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
    assert (result.chat.source, result.chat.disease) == (None, None)


async def test_redis_error_in_tool_is_not_reported_to_model() -> None:
    class BrokenToolCache(FakeToolCache):
        async def get(self, **kwargs: Any) -> Any:
            raise RedisError("redis down")

    agent, model, _ = make_agent([tool_call("get_current_readings"), answer("done")], tool_cache=BrokenToolCache())

    # The SDK wraps tool exceptions in UserError (an AgentsException), which ChatService turns
    # into the temporary-error reply without saving the turn.
    result = await run(agent, "القراءات؟", history=[])

    assert result.response == "معلش، حصلت مشكلة مؤقتة. جرّب تاني بعد شوية."
    assert len(model.calls) == 1
    assert agent.memory.events == []


async def test_plant_tool_with_image_returns_prediction() -> None:
    agent, _, _ = make_agent([tool_call("plant_diseases_detection"), answer("النبات مصاب")])
    image = UploadedImage(filename="p.jpg", content_type="image/jpeg", content=b"secret-image-bytes")

    result = await run(agent, "شخص النبات", history=[], image=image)

    assert json.loads(result.tool_outputs[0].output)["disease"] == "potato early blight"
    assert (result.chat.source, result.chat.disease) == ("yolo", "potato early blight")


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


def test_support_agent_is_a_handoff_not_a_tool() -> None:
    assert farmer_agent.handoffs == [support_agent]
    assert support_agent.name == "Customer Support Agent"
    assert "get_devices_status" not in {tool.name for tool in farmer_agent.tools}
    assert {tool.name for tool in support_agent.tools} == {"get_devices_status"}
    assert support_agent.handoffs == [farmer_agent]


async def test_device_problem_is_handed_off_to_support_which_checks_status() -> None:
    agent, model, renile_client = make_agent(
        [
            tool_call(HANDOFF),
            tool_call("get_devices_status", call_id="call-2"),
            answer("تاريخ تجديد باقة الجهاز انتهى، ومحتاج تشحن الباقة."),
        ]
    )

    result = await run(agent, "جهاز GreenHouse Control Unit مش شغال", history=[])

    assert result.response == "تاريخ تجديد باقة الجهاز انتهى، ومحتاج تشحن الباقة."
    assert renile_client.status_calls == 1
    instructions = [call[0] for call in model.calls]
    assert SUPPORT_MARKER not in instructions[0]
    assert all(SUPPORT_MARKER in text for text in instructions[1:])
    assert "Today's date:" in instructions[1]
    assert [item.name for item in result.tool_outputs] == [HANDOFF, "get_devices_status"]
    assert json.loads(result.tool_outputs[1].output) == DEVICES_STATUS
    assert agent.memory.events == [
        ("user", "جهاز GreenHouse Control Unit مش شغال"),
        ("assistant", "تاريخ تجديد باقة الجهاز انتهى، ومحتاج تشحن الباقة."),
    ]


async def test_support_asks_for_device_before_checking_status() -> None:
    agent, model, renile_client = make_agent([tool_call(HANDOFF), answer("ممكن تقولي اسم الجهاز أو رقمه؟")])

    result = await run(agent, "الجهاز مش شغال", history=[])

    assert result.response == "ممكن تقولي اسم الجهاز أو رقمه؟"
    assert renile_client.status_calls == 0
    assert SUPPORT_MARKER in model.calls[-1][0]


async def test_support_follow_up_starts_at_support_agent_without_handoff() -> None:
    history = [
        {"role": "user", "content": "جهاز GreenHouse Control Unit مش شغال"},
        {"role": "assistant", "content": "هل الجهاز واصله كهربا كويس، واللمبة بتاعته منورة؟", "agent": SUPPORT_AGENT},
    ]
    agent, model, renile_client = make_agent([answer("فريق الدعم الفني هيتواصل معاك في أقرب وقت.")])

    result = await run(agent, "أيوه", history=history)

    assert result.response == "فريق الدعم الفني هيتواصل معاك في أقرب وقت."
    assert len(model.calls) == 1
    assert SUPPORT_MARKER in model.calls[0][0]
    # The agent tag stays in Redis: the model sees only role and content.
    assert model.calls[0][1][:2] == [{"role": item["role"], "content": item["content"]} for item in history]
    assert result.tool_outputs == []
    assert renile_client.status_calls == 0
    assert agent.memory.agents == [SUPPORT_AGENT]


async def test_support_hands_unrelated_message_back_to_farmer() -> None:
    history = [
        {"role": "user", "content": "الجهاز 7 مش شغال"},
        {"role": "assistant", "content": "فريق الدعم الفني هيتواصل معاك في أقرب وقت.", "agent": SUPPORT_AGENT},
    ]
    agent, model, renile_client = make_agent(
        [tool_call(HANDBACK), tool_call("get_current_readings", call_id="call-2"), answer("مفيش بيانات متاحة حالياً.")]
    )

    result = await run(agent, "إيه آخر القراءات؟", history=history)

    assert result.response == "مفيش بيانات متاحة حالياً."
    assert SUPPORT_MARKER in model.calls[0][0]
    assert all(SUPPORT_MARKER not in call[0] for call in model.calls[1:])
    assert renile_client.current_calls == 1
    assert agent.memory.agents == [FARMER_AGENT]


async def test_untagged_history_starts_at_farmer_and_records_support_after_handoff() -> None:
    history = [
        {"role": "user", "content": "جهاز GreenHouse Control Unit مش شغال"},
        {"role": "assistant", "content": "هل الجهاز واصله كهربا كويس، واللمبة بتاعته منورة؟"},
    ]
    agent, model, _ = make_agent([tool_call(HANDOFF), answer("فريق الدعم الفني هيتواصل معاك في أقرب وقت.")])

    result = await run(agent, "أيوه", history=history)

    assert result.response == "فريق الدعم الفني هيتواصل معاك في أقرب وقت."
    assert SUPPORT_MARKER not in model.calls[0][0]
    assert SUPPORT_MARKER in model.calls[-1][0]
    assert model.calls[-1][1][:2] == history
    assert agent.memory.agents == [SUPPORT_AGENT]


async def test_readings_request_with_stale_data_stays_with_farmer_assistant() -> None:
    stale = {"project_name": "Farm 1", "devices": [{"device_name": "Device 1", "readings": [{"age_seconds": 900000}]}]}

    class StaleReNileClient(FakeReNileClient):
        async def get_current_readings(self, jwt: str) -> dict:
            return stale

    agent, model, renile_client = make_agent(
        [tool_call("get_current_readings"), answer("آخر تحديث قديم، وده ممكن يشير لمشكلة اتصال أو توقف الجهاز.")],
        renile_client=StaleReNileClient(),
    )

    result = await run(agent, "إيه آخر القراءات؟", history=[])

    assert [item.name for item in result.tool_outputs] == ["get_current_readings"]
    assert renile_client.status_calls == 0
    assert all(SUPPORT_MARKER not in call[0] for call in model.calls)


async def test_jwt_never_reaches_model_or_logs_on_support_path(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    agent, model, _ = make_agent([tool_call(HANDOFF), tool_call("get_devices_status", call_id="call-2"), answer("done")])

    await run(agent, "الجهاز 7 مش شغال", history=[])

    assert "runtime-jwt" not in repr(model.calls) + caplog.text
