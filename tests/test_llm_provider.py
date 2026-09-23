from types import SimpleNamespace

from agent.agent import strip_thinking
from providers.llm import create_chat_model, create_model_settings


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


def test_chat_model_targets_configured_endpoint_and_model() -> None:
    model = create_chat_model(_settings())  # type: ignore[arg-type]

    assert model.model == "Qwen/Qwen3.6-27B-int4-AutoRound"
    assert str(model._client.base_url) == "http://localhost:5000/v1/"  # noqa: SLF001


def test_model_settings_send_generation_settings() -> None:
    model_settings = create_model_settings(_settings())  # type: ignore[arg-type]

    assert model_settings.temperature == 0.2
    assert model_settings.max_tokens == 1024
    assert model_settings.top_p == 0.8
    assert model_settings.extra_body == {"top_k": 20, "chat_template_kwargs": {"enable_thinking": False}}


def test_model_settings_forward_enable_thinking() -> None:
    model_settings = create_model_settings(_settings(enable_thinking=True))  # type: ignore[arg-type]

    assert model_settings.extra_body["chat_template_kwargs"] == {"enable_thinking": True}


def test_strip_thinking_removes_qwen_reasoning() -> None:
    assert strip_thinking("<think>reasoning</think>الإجابة النهائية") == "الإجابة النهائية"


def test_strip_thinking_preserves_content_without_marker() -> None:
    assert strip_thinking("الإجابة النهائية") == "الإجابة النهائية"
    assert strip_thinking("") == ""
