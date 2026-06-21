import logging
from time import perf_counter
from typing import Any

from openai import AsyncOpenAI

from core.config import Settings

logger = logging.getLogger(__name__)


class LLMProvider:
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
        self._model = settings.llm_model

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> Any:
        started_at = perf_counter()
        tool_names = [tool["function"]["name"] for tool in tools or []]
        logger.info(
            "llm_chat_started model=%s messages=%s tools=%s",
            self._model,
            len(messages),
            tool_names,
        )
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self._client.chat.completions.create(**kwargs)
        assistant_message = response.choices[0].message
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        tool_calls = getattr(assistant_message, "tool_calls", None) or []
        logger.info(
            "llm_chat_completed model=%s latency_ms=%s finish_reason=%s tool_calls=%s response_chars=%s",
            self._model,
            elapsed_ms,
            response.choices[0].finish_reason,
            [tool_call.function.name for tool_call in tool_calls],
            len(assistant_message.content or ""),
        )
        return assistant_message
