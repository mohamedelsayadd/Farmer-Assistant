from types import SimpleNamespace

import pytest

from providers import llm as llm_module
from providers.llm import LLMProvider


class FakeCompletions:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        message = SimpleNamespace(content="تمام", tool_calls=[])
        choice = SimpleNamespace(message=message, finish_reason="stop")
        return SimpleNamespace(choices=[choice])


class FakeAsyncOpenAI:
    last_instance = None

    def __init__(self, *, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.completions = FakeCompletions()
        self.chat = SimpleNamespace(completions=self.completions)
        FakeAsyncOpenAI.last_instance = self


@pytest.mark.asyncio
async def test_llm_provider_sends_generation_settings(monkeypatch) -> None:
    monkeypatch.setattr(llm_module, "AsyncOpenAI", FakeAsyncOpenAI)
    settings = SimpleNamespace(
        llm_api_key="EMPTY",
        llm_base_url="http://localhost:5000/v1",
        llm_model="Qwen/Qwen3.6-27B-int4-AutoRound",
        llm_enable_thinking=False,
        llm_temperature=0.2,
        llm_max_tokens=1024,
        llm_top_p=0.8,
        llm_top_k=20,
    )
    provider = LLMProvider(settings)

    await provider.chat([{"role": "user", "content": "السلام عليكم"}])

    request_kwargs = FakeAsyncOpenAI.last_instance.completions.kwargs
    assert request_kwargs["model"] == "Qwen/Qwen3.6-27B-int4-AutoRound"
    assert request_kwargs["temperature"] == 0.2
    assert request_kwargs["max_tokens"] == 1024
    assert request_kwargs["top_p"] == 0.8
    assert request_kwargs["extra_body"] == {
        "top_k": 20,
        "chat_template_kwargs": {
            "enable_thinking": False,
        },
    }


@pytest.mark.asyncio
async def test_llm_provider_keeps_tool_choice_when_tools_are_passed(monkeypatch) -> None:
    monkeypatch.setattr(llm_module, "AsyncOpenAI", FakeAsyncOpenAI)
    settings = SimpleNamespace(
        llm_api_key="EMPTY",
        llm_base_url="http://localhost:5000/v1",
        llm_model="Qwen/Qwen3.6-27B-int4-AutoRound",
        llm_enable_thinking=False,
        llm_temperature=0.2,
        llm_max_tokens=1024,
        llm_top_p=0.8,
        llm_top_k=20,
    )
    provider = LLMProvider(settings)
    tools = [{"type": "function", "function": {"name": "get_current_readings"}}]

    await provider.chat([{"role": "user", "content": "الحرارة كام؟"}], tools=tools)

    request_kwargs = FakeAsyncOpenAI.last_instance.completions.kwargs
    assert request_kwargs["tools"] == tools
    assert request_kwargs["tool_choice"] == "auto"
