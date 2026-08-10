import json
import logging
from dataclasses import dataclass
from datetime import date
from time import perf_counter
from typing import Any, NotRequired, TypedDict

import httpx

from agent.prompts import SYSTEM_PROMPT
from agent.tools import OPENAI_TOOLS, execute_devices_ids_tool, execute_tool
from core.logging import json_preview
from memory.redis_memory import MemoryMessage
from memory.tool_cache import ToolCache
from providers.llm import LLMProvider
from providers.renile_client import ReNileClient

logger = logging.getLogger(__name__)
CURRENT_TOOL_NAMES = {"get_current_readings"}
HISTORICAL_TOOL_NAMES = {"get_devices_ids", "get_last_duration_summary", "get_specific_time_readings"}
HISTORICAL_READING_TOOL_NAMES = {"get_last_duration_summary", "get_specific_time_readings"}
MAX_TOOL_ROUNDS = 4
FALLBACK_RESPONSE = "معلش، مش قادر أوصل لإجابة واضحة دلوقتي."


class AgentState(TypedDict):
    conversation_id: str
    jwt: str
    history: list[MemoryMessage]
    user_message: str
    messages: list[dict[str, Any]]
    assistant_message: NotRequired[Any]
    tool_results: NotRequired[list[dict[str, Any]]]
    tool_contexts: NotRequired[list["ToolContext"]]
    final_response: NotRequired[str]


@dataclass(frozen=True)
class ToolContext:
    tool_name: str
    content: str


@dataclass(frozen=True)
class AgentResult:
    response: str
    tool_contexts: list[ToolContext]


class FarmerAssistantAgent:
    def __init__(self, llm: LLMProvider, renile_client: ReNileClient, tool_cache: ToolCache) -> None:
        self._llm = llm
        self._renile_client = renile_client
        self._tool_cache = tool_cache

    async def run(
        self,
        conversation_id: str,
        jwt: str,
        user_message: str,
        history: list[MemoryMessage],
    ) -> AgentResult:
        started_at = perf_counter()
        logger.info(
            "agent_run_started history_messages=%s user_message_chars=%s",
            len(history),
            len(user_message),
        )
        state: AgentState = {
            "conversation_id": conversation_id,
            "jwt": jwt,
            "history": history,
            "user_message": user_message,
            "messages": self._build_messages(history, user_message),
        }
        tool_contexts: list[ToolContext] = []
        final_response = FALLBACK_RESPONSE

        for tool_round in range(MAX_TOOL_ROUNDS + 1):
            agent_update = await self._agent_node(state)
            state.update(agent_update)
            assistant_message = state["assistant_message"]
            tool_path = self._tool_path(state)

            if tool_path == "final":
                final_response = assistant_message.content or FALLBACK_RESPONSE
                break
            if tool_round == MAX_TOOL_ROUNDS:
                logger.warning("agent_tool_round_limit_reached max_rounds=%s", MAX_TOOL_ROUNDS)
                break

            if tool_path == "current_tools":
                tool_update = await self._current_tools_node(state)
            elif tool_path == "historical_tools":
                tool_update = await self._historical_tools_node(state)
            else:
                final_response = assistant_message.content or FALLBACK_RESPONSE
                break

            state.update(tool_update)
            tool_contexts.extend(tool_update.get("tool_contexts", []))
            state["messages"] = self._messages_after_tools(state)

        elapsed_ms = int((perf_counter() - started_at) * 1000)
        logger.info(
            "agent_run_completed response_chars=%s tool_contexts=%s latency_ms=%s",
            len(final_response),
            len(tool_contexts),
            elapsed_ms,
        )
        return AgentResult(response=final_response, tool_contexts=tool_contexts)

    async def _agent_node(self, state: AgentState) -> dict[str, Any]:
        logger.info("agent_node_started messages=%s available_tools=%s", len(state["messages"]), len(OPENAI_TOOLS))
        assistant_message = await self._llm.chat(state["messages"], tools=OPENAI_TOOLS)
        tool_calls = getattr(assistant_message, "tool_calls", None) or []
        logger.info(
            "agent_node_completed tool_calls=%s response_chars=%s",
            [tool_call.function.name for tool_call in tool_calls],
            len(assistant_message.content or ""),
        )
        return {"assistant_message": assistant_message}

    async def _current_tools_node(self, state: AgentState) -> dict[str, Any]:
        logger.info("current_tools_node_started")
        return await self._execute_tool_calls(state, CURRENT_TOOL_NAMES)

    async def _historical_tools_node(self, state: AgentState) -> dict[str, Any]:
        logger.info("historical_tools_node_started")
        return await self._execute_tool_calls(state, HISTORICAL_TOOL_NAMES)

    async def _execute_tool_calls(self, state: AgentState, allowed_tool_names: set[str]) -> dict[str, Any]:
        assistant_message = state["assistant_message"]
        tool_results: list[dict[str, Any]] = []
        tool_contexts: list[ToolContext] = []
        for tool_call in assistant_message.tool_calls or []:
            if tool_call.function.name not in allowed_tool_names:
                self._log_skipped_tool_call(tool_call, allowed_tool_names)
                continue
            tool_result, tool_context = await self._execute_tool_call(state, tool_call)
            tool_results.append(tool_result)
            if tool_context:
                tool_contexts.append(tool_context)

        return {"tool_results": tool_results, "tool_contexts": tool_contexts}

    async def _execute_tool_call(self, state: AgentState, tool_call: Any) -> tuple[dict[str, Any], ToolContext | None]:
        try:
            logger.info(
                "tool_call_started tool_call_id=%s tool_name=%s raw_arguments=%s",
                tool_call.id,
                tool_call.function.name,
                tool_call.function.arguments,
            )
            arguments = json.loads(tool_call.function.arguments or "{}")
            if tool_call.function.name in HISTORICAL_READING_TOOL_NAMES:
                arguments, fallback_tool_result = await self._resolve_historical_arguments(state, arguments)
                if fallback_tool_result is not None:
                    return self._successful_tool_result(tool_call, fallback_tool_result, tool_name="get_devices_ids")

            cached_tool_result = await self._tool_cache.get(
                conversation_id=state["conversation_id"],
                tool_name=tool_call.function.name,
                arguments=arguments,
            )
            if cached_tool_result is not None:
                return self._successful_tool_result(tool_call, cached_tool_result)

            tool_result = await execute_tool(
                tool_call.function.name,
                jwt=state["jwt"],
                arguments=arguments,
                renile_client=self._renile_client,
            )
            await self._tool_cache.set(
                conversation_id=state["conversation_id"],
                tool_name=tool_call.function.name,
                arguments=arguments,
                result=tool_result,
            )
            return self._successful_tool_result(tool_call, tool_result)
        except (json.JSONDecodeError, ValueError, httpx.HTTPError):
            logger.exception("tool_call_failed tool_call_id=%s tool_name=%s", tool_call.id, tool_call.function.name)
            return self._failed_tool_result(tool_call), None

    @staticmethod
    def _successful_tool_result(
        tool_call: Any,
        tool_result: Any,
        tool_name: str | None = None,
    ) -> tuple[dict[str, Any], ToolContext]:
        resolved_tool_name = tool_name or tool_call.function.name
        logger.info(
            "tool_call_completed tool_call_id=%s tool_name=%s result_preview=%s",
            tool_call.id,
            resolved_tool_name,
            json_preview(tool_result),
        )
        content = json.dumps(tool_result, ensure_ascii=False)
        return (
            {"role": "tool", "tool_call_id": tool_call.id, "name": resolved_tool_name, "content": content},
            ToolContext(tool_name=resolved_tool_name, content=content),
        )

    async def _resolve_historical_arguments(
        self,
        state: AgentState,
        arguments: dict[str, Any],
    ) -> tuple[dict[str, Any], Any | None]:
        raw_device_id = str(arguments.get("device_id", "")).strip()
        devices_result = await self._cached_or_fresh_devices_result(state)
        # The devices tool result is the backend array itself. A dict here means a
        # stale pre-passthrough cache entry, so fall back to showing the device list.
        if not isinstance(devices_result, list):
            logger.warning("historical_device_resolution_invalid_cached_devices_result")
            return arguments, devices_result

        resolved_device_id = self._resolve_device_id(raw_device_id, devices_result)
        if resolved_device_id:
            return {**arguments, "device_id": resolved_device_id}, None

        logger.warning("historical_device_resolution_failed raw_device_id=%s", raw_device_id)
        return arguments, devices_result

    async def _cached_or_fresh_devices_result(self, state: AgentState) -> Any:
        arguments: dict[str, Any] = {}
        cached_devices_result = await self._tool_cache.get(
            conversation_id=state["conversation_id"],
            tool_name="get_devices_ids",
            arguments=arguments,
        )
        if cached_devices_result is not None:
            return cached_devices_result

        devices_result = await execute_devices_ids_tool(jwt=state["jwt"], renile_client=self._renile_client)
        await self._tool_cache.set(
            conversation_id=state["conversation_id"],
            tool_name="get_devices_ids",
            arguments=arguments,
            result=devices_result,
        )
        return devices_result

    @staticmethod
    def _resolve_device_id(raw_device_id: str, devices: list[dict[str, Any]]) -> str | None:
        if not raw_device_id:
            return None
        for device in devices:
            device_id = str(device.get("_id", "")).strip()
            if raw_device_id == device_id:
                return device_id

        # Enumerate the full array: the model numbers the list it was shown verbatim,
        # so skipping entries here would shift indices against its numbering.
        lowered_raw_device_id = raw_device_id.casefold()
        for index, device in enumerate(devices, start=1):
            device_name = str(device.get("name", "")).strip()
            device_id = str(device.get("_id", "")).strip()
            if not device_id:
                continue
            if raw_device_id == str(index) or lowered_raw_device_id == device_name.casefold():
                return device_id
        return None

    @staticmethod
    def _failed_tool_result(tool_call: Any) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_call.function.name,
            "content": "Tool failed temporarily.",
        }

    @staticmethod
    def _log_skipped_tool_call(tool_call: Any, allowed_tool_names: set[str]) -> None:
        logger.info(
            "tool_call_skipped tool_call_id=%s tool_name=%s allowed_tools=%s",
            tool_call.id,
            tool_call.function.name,
            sorted(allowed_tool_names),
        )

    @staticmethod
    def _messages_after_tools(state: AgentState) -> list[dict[str, Any]]:
        tool_results = state.get("tool_results", [])
        assistant_message = state["assistant_message"]
        return [
            *state["messages"],
            assistant_message.model_dump(exclude_none=True),
            *tool_results,
        ]

    @staticmethod
    def _tool_path(state: AgentState) -> str:
        assistant_message = state["assistant_message"]
        tool_calls = getattr(assistant_message, "tool_calls", None) or []
        if not tool_calls:
            logger.info("tool_path_selected path=final")
            return "final"
        tool_name = tool_calls[0].function.name
        if tool_name in CURRENT_TOOL_NAMES:
            logger.info("tool_path_selected path=current_tools tool_name=%s", tool_name)
            return "current_tools"
        if tool_name in HISTORICAL_TOOL_NAMES:
            logger.info("tool_path_selected path=historical_tools tool_name=%s", tool_name)
            return "historical_tools"
        logger.warning("tool_path_selected path=final unknown_tool=%s", tool_name)
        return "final"

    @staticmethod
    def _build_messages(history: list[MemoryMessage], user_message: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": FarmerAssistantAgent._system_prompt(history)}
        ]
        messages.extend(FarmerAssistantAgent._history_message(message) for message in history)
        messages.append({"role": "user", "content": user_message})
        return messages

    @staticmethod
    def _system_prompt(history: list[MemoryMessage] | None = None) -> str:
        current_date = date.today().isoformat()
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"تاريخ النهاردة: {current_date}. استخدم التاريخ ده عشان تفهم عبارات زي امبارح، "
            "آخر أسبوع، آخر 3 أسابيع، آخر فترة، من يومين، يوم الأحد اللي فات، ومن شهر 1 لشهر 5."
        )

        return prompt

    @staticmethod
    def _history_message(message: MemoryMessage) -> dict[str, Any]:
        return {"role": message["role"], "content": message["content"]}
