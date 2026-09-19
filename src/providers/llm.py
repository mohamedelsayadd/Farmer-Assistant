from langchain_openai import ChatOpenAI

from core.config import Settings


def create_chat_model(settings: Settings) -> ChatOpenAI:
    """OpenAI-compatible chat model (vLLM/Qwen) with the backend's sampling settings."""
    return ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        top_p=settings.llm_top_p,
        extra_body={
            "top_k": settings.llm_top_k,
            "chat_template_kwargs": {"enable_thinking": settings.llm_enable_thinking},
        },
    )
