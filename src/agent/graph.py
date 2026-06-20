import json
import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Any, NotRequired, TypedDict

import httpx
from langgraph.graph import END, StateGraph

from agent.prompts import SYSTEM_PROMPT
from agent.tools import OPENAI_TOOLS, execute_tool
from core.logging import json_preview
from memory.redis_memory import MemoryMessage
from providers.llm import LLMProvider
from providers.renile_client import ReNileClient

logger = logging.getLogger(__name__)


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
        graph.add_node("tools", self._tools_node)
        graph.add_node("final", self._final_node)
        graph.set_entry_point("agent")
        graph.add_conditional_edges("agent", self._should_call_tools, {"tools": "tools", "final": "final"})
        graph.add_edge("tools", "final")
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

    async def _tools_node(self, state: AgentState) -> dict[str, Any]:
        assistant_message = state["assistant_message"]
        tool_results: list[dict[str, Any]] = []
        tool_contexts: list[ToolContext] = []
        for tool_call in assistant_message.tool_calls or []:
            try:
                logger.info(
                    "tool_call_started tool_call_id=%s tool_name=%s raw_arguments=%s",
                    tool_call.id,
                    tool_call.function.name,
                    tool_call.function.arguments,
                )
                arguments = json.loads(tool_call.function.arguments or "{}")
                result = await execute_tool(
                    tool_call.function.name,
                    jwt=state["jwt"],
                    arguments=arguments,
                    renile_client=self._renile_client,
                )
                logger.info(
                    "tool_call_completed tool_call_id=%s tool_name=%s result_preview=%s",
                    tool_call.id,
                    tool_call.function.name,
                    json_preview(result),
                )
                tool_contexts.append(
                    ToolContext(
                        tool_name=tool_call.function.name,
                        content=json.dumps(result, ensure_ascii=False),
                    )
                )
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
            except (json.JSONDecodeError, ValueError, httpx.HTTPError):
                logger.exception(
                    "tool_call_failed tool_call_id=%s tool_name=%s",
                    tool_call.id,
                    tool_call.function.name,
                )
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": "Tool failed temporarily.",
                    }
                )

        return {"tool_results": tool_results, "tool_contexts": tool_contexts}

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
    def _should_call_tools(state: AgentState) -> str:
        assistant_message = state["assistant_message"]
        if getattr(assistant_message, "tool_calls", None):
            return "tools"
        return "final"

    @staticmethod
    def _build_messages(history: list[MemoryMessage], user_message: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(FarmerAssistantAgent._history_message(message) for message in history)
        messages.append({"role": "user", "content": user_message})
        return messages

    @staticmethod
    def _history_message(message: MemoryMessage) -> dict[str, Any]:
        if message["role"] == "tool_context":
            tool_name = message.get("tool_name", "unknown_tool")
            logger.info("agent_context_included tool_name=%s content_chars=%s", tool_name, len(message["content"]))
            return {
                "role": "system",
                "content": (
                    f"Cached tool result from {tool_name}. Use it for follow-up questions if relevant. "
                    "Do not call the API again unless the user clearly asks for fresh or updated readings.\n\n"
                    f"{message['content']}"
                ),
            }
        return {"role": message["role"], "content": message["content"]}
