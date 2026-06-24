import logging
from time import perf_counter
from typing import Any, AsyncIterator

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
        self._enable_thinking = settings.llm_enable_thinking
        self._temperature = settings.llm_temperature
        self._max_tokens = settings.llm_max_tokens
        self._top_p = settings.llm_top_p
        self._top_k = settings.llm_top_k

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
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "top_p": self._top_p,
            "extra_body": {
                "top_k": self._top_k,
                "chat_template_kwargs": {
                    "enable_thinking": self._enable_thinking,
                },
            },
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self._client.chat.completions.create(**kwargs)
        assistant_message = response.choices[0].message
        assistant_message.content = self._strip_thinking(assistant_message.content)
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

    async def stream_chat(self, messages: list[dict[str, Any]]) -> AsyncIterator[str]:
        started_at = perf_counter()
        logger.info(
            "llm_stream_chat_started model=%s messages=%s",
            self._model,
            len(messages),
        )
        response_chars = 0
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "top_p": self._top_p,
            "stream": True,
            "extra_body": {
                "top_k": self._top_k,
                "chat_template_kwargs": {
                    "enable_thinking": self._enable_thinking,
                },
            },
        }
        stream = await self._client.chat.completions.create(**kwargs)

        async for chunk in stream:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if not content:
                continue
            response_chars += len(content)
            yield content

        elapsed_ms = int((perf_counter() - started_at) * 1000)
        logger.info(
            "llm_stream_chat_completed model=%s latency_ms=%s response_chars=%s",
            self._model,
            elapsed_ms,
            response_chars,
        )

    @staticmethod
    def _strip_thinking(content: str | None) -> str | None:
        if not content or "</think>" not in content:
            return content
        return content.rsplit("</think>", maxsplit=1)[-1].strip()
