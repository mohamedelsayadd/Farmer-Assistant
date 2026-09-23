from agents import ModelSettings, OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from core.config import Settings


def create_chat_model(settings: Settings) -> OpenAIChatCompletionsModel:
    """OpenAI-compatible chat model (vLLM/Qwen) over the Chat Completions API."""
    client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)
    return OpenAIChatCompletionsModel(model=settings.llm_model, openai_client=client)


def create_model_settings(settings: Settings) -> ModelSettings:
    """The backend's sampling settings, sent on every model call."""
    return ModelSettings(
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        top_p=settings.llm_top_p,
        extra_body={
            "top_k": settings.llm_top_k,
            "chat_template_kwargs": {"enable_thinking": settings.llm_enable_thinking},
        },
    )
