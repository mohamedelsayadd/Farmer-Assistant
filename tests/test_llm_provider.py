from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from agent.agent import strip_thinking
from providers.llm import create_chat_model


def _settings(enable_thinking: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        llm_api_key="EMPTY",
        llm_base_url="http://localhost:5000/v1",
        llm_model="Qwen/Qwen3.6-27B-int4-AutoRound",
        llm_enable_thinking=enable_thinking,
        llm_temperature=0.2,
        llm_max_tokens=1024,
        llm_top_p=0.8,
        llm_top_k=20,
    )


def test_chat_model_sends_generation_settings() -> None:
    model = create_chat_model(_settings())  # type: ignore[arg-type]

    payload = model._get_request_payload([HumanMessage("السلام عليكم")])  # noqa: SLF001
    assert model.openai_api_base == "http://localhost:5000/v1"
    assert payload["model"] == "Qwen/Qwen3.6-27B-int4-AutoRound"
    assert payload["temperature"] == 0.2
    assert payload["max_completion_tokens"] == 1024
    assert payload["top_p"] == 0.8
    assert payload["extra_body"] == {"top_k": 20, "chat_template_kwargs": {"enable_thinking": False}}


def test_chat_model_forwards_enable_thinking() -> None:
    model = create_chat_model(_settings(enable_thinking=True))  # type: ignore[arg-type]

    assert model._default_params["extra_body"]["chat_template_kwargs"] == {"enable_thinking": True}  # noqa: SLF001


def test_strip_thinking_removes_qwen_reasoning() -> None:
    assert strip_thinking("<think>reasoning</think>الإجابة النهائية") == "الإجابة النهائية"


def test_strip_thinking_preserves_content_without_marker() -> None:
    assert strip_thinking("الإجابة النهائية") == "الإجابة النهائية"
    assert strip_thinking("") == ""
