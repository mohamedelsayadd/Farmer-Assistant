import json
import logging
from dataclasses import dataclass
from datetime import date
from time import perf_counter
from typing import Any, NotRequired, TypedDict

import httpx
from langgraph.graph import END, StateGraph

from agent.prompts import SYSTEM_PROMPT
from agent.tools import OPENAI_TOOLS, execute_devices_ids_tool, execute_tool
from core.logging import json_preview
from memory.redis_memory import MemoryMessage
from providers.llm import LLMProvider
from providers.renile_client import ReNileClient

logger = logging.getLogger(__name__)
CURRENT_TOOL_NAMES = {"get_current_readings"}
HISTORICAL_TOOL_NAMES = {"get_devices_ids", "get_last_duration_summary", "get_specific_time_readings"}
HISTORICAL_READING_TOOL_NAMES = {"get_last_duration_summary", "get_specific_time_readings"}


class AgentState(TypedDict):
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
    def __init__(self, llm: LLMProvider, renile_client: ReNileClient) -> None:
        self._llm = llm
        self._renile_client = renile_client
        self._graph = self._build_graph()

    async def run(self, jwt: str, user_message: str, history: list[MemoryMessage]) -> AgentResult:
        started_at = perf_counter()
        logger.info(
            "agent_run_started history_messages=%s user_message_chars=%s",
            len(history),
            len(user_message),
        )
        initial_state: AgentState = {
            "jwt": jwt,
            "history": history,
            "user_message": user_message,
            "messages": self._build_messages(history, user_message),
        }
        result = await self._graph.ainvoke(initial_state)
        final_response = result.get("final_response") or "معلش، حصلت مشكلة مؤقتة. جرّب تاني بعد شوية."
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        tool_contexts = result.get("tool_contexts", [])
        logger.info(
            "agent_run_completed response_chars=%s tool_contexts=%s latency_ms=%s",
            len(final_response),
            len(tool_contexts),
            elapsed_ms,
        )
        return AgentResult(response=final_response, tool_contexts=tool_contexts)

    def _build_graph(self) -> Any:
        graph = StateGraph(AgentState)
        graph.add_node("agent", self._agent_node)
        graph.add_node("current_tools", self._current_tools_node)
        graph.add_node("historical_tools", self._historical_tools_node)
        graph.add_node("final", self._final_node)
        graph.set_entry_point("agent")
        graph.add_conditional_edges(
            "agent",
            self._tool_path,
            {"current_tools": "current_tools", "historical_tools": "historical_tools", "final": "final"},
        )
        graph.add_edge("current_tools", "final")
        graph.add_edge("historical_tools", "final")
        graph.add_edge("final", END)
        return graph.compile()

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
            tool_result = await execute_tool(
                tool_call.function.name,
                jwt=state["jwt"],
                arguments=arguments,
                renile_client=self._renile_client,
            )
            return self._successful_tool_result(tool_call, tool_result)
        except (json.JSONDecodeError, ValueError, httpx.HTTPError):
            logger.exception("tool_call_failed tool_call_id=%s tool_name=%s", tool_call.id, tool_call.function.name)
            return self._failed_tool_result(tool_call), None

    @staticmethod
    def _successful_tool_result(
        tool_call: Any,
        tool_result: dict[str, Any],
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
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        raw_device_id = str(arguments.get("device_id", "")).strip()
        known_devices = self._devices_from_history(state["history"])

        resolved_device_id = self._resolve_device_id(raw_device_id, known_devices)
        if resolved_device_id:
            return {**arguments, "device_id": resolved_device_id}, None

        devices_result = await execute_devices_ids_tool(jwt=state["jwt"], renile_client=self._renile_client)
        fetched_devices = devices_result.get("devices", [])
        if not isinstance(fetched_devices, list):
            logger.warning("historical_device_resolution_invalid_devices_result")
            return arguments, devices_result

        resolved_device_id = self._resolve_device_id(raw_device_id, fetched_devices)
        if resolved_device_id:
            logger.info("historical_device_name_resolved_to_id")
            return {**arguments, "device_id": resolved_device_id}, None

        logger.warning("historical_device_resolution_failed raw_device_id=%s", raw_device_id)
        return arguments, devices_result

    @staticmethod
    def _devices_from_history(history: list[MemoryMessage]) -> list[dict[str, Any]]:
        devices: list[dict[str, Any]] = []
        for message in history:
            if message["role"] != "tool_context" or message.get("tool_name") != "get_devices_ids":
                continue
            try:
                content = json.loads(message["content"])
            except json.JSONDecodeError:
                logger.warning("cached_devices_context_invalid_json")
                continue
            cached_devices = content.get("devices", [])
            if isinstance(cached_devices, list):
                devices.extend(device for device in cached_devices if isinstance(device, dict))
        return devices

    @staticmethod
    def _resolve_device_id(raw_device_id: str, devices: list[dict[str, Any]]) -> str | None:
        if not raw_device_id:
            return None
        for device in devices:
            device_id = str(device.get("device_id", "")).strip()
            if raw_device_id == device_id:
                return device_id

        lowered_raw_device_id = raw_device_id.casefold()
        for index, device in enumerate(devices, start=1):
            device_name = str(device.get("device_name", "")).strip()
            device_id = str(device.get("device_id", "")).strip()
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

    async def _final_node(self, state: AgentState) -> dict[str, str]:
        assistant_message = state["assistant_message"]
        tool_results = state.get("tool_results", [])
        logger.info("final_node_started tool_results=%s", len(tool_results))

        if not tool_results:
            final_response = assistant_message.content or "ممكن توضّحلي سؤالك أكتر؟"
            logger.info("final_node_completed used_tools=false response_chars=%s", len(final_response))
            return {"final_response": final_response}

        messages = [
            *state["messages"],
            assistant_message.model_dump(exclude_none=True),
            *tool_results,
        ]
        final_message = await self._llm.chat(messages)
        final_response = final_message.content or "معلش، مش قادر أوصل لإجابة واضحة دلوقتي."
        logger.info("final_node_completed used_tools=true response_chars=%s", len(final_response))
        return {"final_response": final_response}

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
        messages.extend(FarmerAssistantAgent._history_message(message) for message in history if message["role"] != "tool_context")
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

        cached_contexts = FarmerAssistantAgent._cached_tool_contexts(history or [])
        if cached_contexts:
            prompt = f"{prompt}\n\n{cached_contexts}"
        return prompt

    @staticmethod
    def _cached_tool_contexts(history: list[MemoryMessage]) -> str:
        contexts: list[str] = []
        for message in history:
            if message["role"] != "tool_context":
                continue
            tool_name = message.get("tool_name", "unknown_tool")
            logger.info("agent_context_included tool_name=%s content_chars=%s", tool_name, len(message["content"]))
            contexts.append(
                f"Cached tool result from {tool_name}. Use it for follow-up questions if relevant. "
                "Do not call the API again unless the user clearly asks for fresh or updated readings.\n\n"
                f"{message['content']}"
            )
        if not contexts:
            return ""
        return "\n\n".join(contexts)

    @staticmethod
    def _history_message(message: MemoryMessage) -> dict[str, Any]:
        return {"role": message["role"], "content": message["content"]}
