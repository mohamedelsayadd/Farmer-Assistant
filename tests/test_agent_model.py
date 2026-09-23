from agent.agent import farmer_agent, model_settings, strip_thinking
from conftest import BASE_ENV


def test_agent_uses_configured_model_and_endpoint() -> None:
    assert farmer_agent.model.model == BASE_ENV["LLM_MODEL"]
    assert str(farmer_agent.model._client.base_url) == BASE_ENV["LLM_BASE_URL"] + "/"  # noqa: SLF001


def test_agent_sends_generation_settings() -> None:
    assert farmer_agent.model_settings is model_settings
    assert model_settings.temperature == 0.2
    assert model_settings.max_tokens == 1024
    assert model_settings.top_p == 0.8
    assert model_settings.extra_body == {"top_k": 20, "chat_template_kwargs": {"enable_thinking": False}}


def test_strip_thinking_removes_qwen_reasoning() -> None:
    assert strip_thinking("<think>reasoning</think>الإجابة النهائية") == "الإجابة النهائية"


def test_strip_thinking_preserves_content_without_marker() -> None:
    assert strip_thinking("الإجابة النهائية") == "الإجابة النهائية"
    assert strip_thinking("") == ""
