import json
import logging
from typing import Any, NotRequired, TypedDict

from langgraph.graph import END, StateGraph

from agent.prompts import SYSTEM_PROMPT
from agent.tools import OPENAI_TOOLS, execute_tool
from memory.redis_memory import MemoryMessage
from providers.llm import LLMProvider

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    jwt: str
    history: list[MemoryMessage]
    user_message: str
    messages: list[dict[str, Any]]
    assistant_message: NotRequired[Any]
    tool_results: NotRequired[list[dict[str, Any]]]
    final_response: NotRequired[str]


class FarmerAssistantAgent:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm
        self._graph = self._build_graph()

    async def run(self, jwt: str, user_message: str, history: list[MemoryMessage]) -> str:
        initial_state: AgentState = {
            "jwt": jwt,
            "history": history,
            "user_message": user_message,
            "messages": self._build_messages(history, user_message),
        }
        result = await self._graph.ainvoke(initial_state)
        return result.get("final_response") or "معلش، حصلت مشكلة مؤقتة. جرّب تاني بعد شوية."

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
        assistant_message = await self._llm.chat(state["messages"], tools=OPENAI_TOOLS)
        return {"assistant_message": assistant_message}

    async def _tools_node(self, state: AgentState) -> dict[str, Any]:
        assistant_message = state["assistant_message"]
        tool_results: list[dict[str, Any]] = []
        for tool_call in assistant_message.tool_calls or []:
            try:
                arguments = json.loads(tool_call.function.arguments or "{}")
                result = await execute_tool(tool_call.function.name, jwt=state["jwt"], arguments=arguments)
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
            except (json.JSONDecodeError, ValueError):
                logger.exception("Tool execution failed", extra={"tool_name": tool_call.function.name})
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": "Tool failed temporarily.",
                    }
                )

        return {"tool_results": tool_results}

    async def _final_node(self, state: AgentState) -> dict[str, str]:
        assistant_message = state["assistant_message"]
        tool_results = state.get("tool_results", [])

        if not tool_results:
            return {"final_response": assistant_message.content or "ممكن توضّحلي سؤالك أكتر؟"}

        messages = [
            *state["messages"],
            assistant_message.model_dump(exclude_none=True),
            *tool_results,
        ]
        final_message = await self._llm.chat(messages)
        return {"final_response": final_message.content or "معلش، مش قادر أوصل لإجابة واضحة دلوقتي."}

    @staticmethod
    def _should_call_tools(state: AgentState) -> str:
        assistant_message = state["assistant_message"]
        if getattr(assistant_message, "tool_calls", None):
            return "tools"
        return "final"

    @staticmethod
    def _build_messages(history: list[MemoryMessage], user_message: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend({"role": message["role"], "content": message["content"]} for message in history)
        messages.append({"role": "user", "content": user_message})
        return messages
