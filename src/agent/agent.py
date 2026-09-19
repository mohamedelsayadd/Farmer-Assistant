import logging
from dataclasses import dataclass
from datetime import date
from time import perf_counter
from typing import Any

import httpx
from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import (
    ModelRequest,
    ToolCallRequest,
    ToolErrorMiddleware,
    after_model,
    dynamic_prompt,
    wrap_model_call,
)
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from agent.prompts import SYSTEM_PROMPT
from agent.tools import TOOLS, AgentContext
from memory.redis_memory import MemoryMessage
from memory.tool_cache import ToolCache
from models.schemas.chat import UploadedImage
from providers.plant_disease_client import PlantDiseaseClient
from providers.renile_client import ReNileClient

logger = logging.getLogger(__name__)

IMAGE_ATTACHMENT_MARKER = "[The user attached a plant image with this message.]"
MAX_TOOL_ROUNDS = 4
FALLBACK_RESPONSE = "معلش، مش قادر أوصل لإجابة واضحة دلوقتي."
TOOL_FAILED_MESSAGE = "Tool failed temporarily."


@dataclass(frozen=True)
class AgentResult:
    response: str
    tool_messages: list[ToolMessage]


def system_prompt() -> str:
    # Rebuilt per request so relative Arabic dates ("امبارح", "آخر أسبوع") resolve against today.
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"تاريخ النهاردة: {date.today().isoformat()}. استخدم التاريخ ده عشان تفهم عبارات زي امبارح، "
        "آخر أسبوع، آخر 3 أسابيع، آخر فترة، من يومين، يوم الأحد اللي فات، ومن شهر 1 لشهر 5."
    )


def build_messages(
    history: list[MemoryMessage],
    user_message: str,
    image: UploadedImage | None = None,
) -> list[BaseMessage]:
    messages: list[BaseMessage] = [
        HumanMessage(item["content"]) if item["role"] == "user" else AIMessage(item["content"]) for item in history
    ]
    if image is not None:
        user_message = f"{user_message}\n\n{IMAGE_ATTACHMENT_MARKER}"
    messages.append(HumanMessage(user_message))
    return messages


def strip_thinking(content: Any) -> Any:
    if not isinstance(content, str) or "</think>" not in content:
        return content
    return content.rsplit("</think>", maxsplit=1)[-1].strip()


@dynamic_prompt
def _date_aware_prompt(request: ModelRequest) -> str:
    return system_prompt()


@wrap_model_call
async def _strip_thinking(request: ModelRequest, handler: Any) -> Any:
    response = await handler(request)
    for message in response.result:
        if isinstance(message, AIMessage):
            message.content = strip_thinking(message.content)
    return response


@after_model(can_jump_to=["end"])
def _limit_tool_rounds(state: AgentState, runtime: Runtime[AgentContext]) -> dict[str, Any] | None:
    # Allow MAX_TOOL_ROUNDS tool rounds; if the model still wants tools on the
    # following call, stop and let run() answer with the fallback.
    messages = state["messages"]
    last_human = max(i for i, message in enumerate(messages) if isinstance(message, HumanMessage))
    model_calls = sum(isinstance(message, AIMessage) for message in messages[last_human:])
    if model_calls > MAX_TOOL_ROUNDS and messages[-1].tool_calls:
        logger.warning("agent_tool_round_limit_reached max_rounds=%s", MAX_TOOL_ROUNDS)
        return {"jump_to": "end"}
    return None


def _tool_failed(error: Exception, request: ToolCallRequest) -> str | None:
    if isinstance(error, (ValueError, httpx.HTTPError)):
        logger.exception(
            "tool_call_failed tool_call_id=%s tool_name=%s",
            request.tool_call["id"],
            request.tool_call["name"],
            exc_info=error,
        )
        return TOOL_FAILED_MESSAGE
    return None


class FarmerAssistantAgent:
    def __init__(
        self,
        model: BaseChatModel,
        renile_client: ReNileClient,
        tool_cache: ToolCache,
        plant_disease_client: PlantDiseaseClient | None = None,
        callbacks: list[BaseCallbackHandler] | None = None,
    ) -> None:
        self._renile_client = renile_client
        self._tool_cache = tool_cache
        self._plant_disease_client = plant_disease_client
        self._callbacks = callbacks or []
        self._graph = create_agent(
            model,
            tools=TOOLS,
            context_schema=AgentContext,
            middleware=[_date_aware_prompt, _strip_thinking, _limit_tool_rounds, ToolErrorMiddleware(_tool_failed)],
            name="farmer-assistant",
        )

    async def run(
        self,
        conversation_id: str,
        jwt: str,
        user_message: str,
        history: list[MemoryMessage],
        image: UploadedImage | None = None,
    ) -> AgentResult:
        started_at = perf_counter()
        logger.info("agent_run_started history_messages=%s user_message_chars=%s", len(history), len(user_message))
        input_messages = build_messages(history, user_message, image)
        context = AgentContext(
            conversation_id=conversation_id,
            jwt=jwt,
            renile_client=self._renile_client,
            tool_cache=self._tool_cache,
            plant_disease_client=self._plant_disease_client,
            image=image,
        )
        state = await self._graph.ainvoke(
            {"messages": input_messages},
            context=context,
            config={"callbacks": self._callbacks},
        )

        new_messages = state["messages"][len(input_messages) :]
        tool_messages = [message for message in new_messages if isinstance(message, ToolMessage)]
        last = new_messages[-1] if new_messages else None
        final = isinstance(last, AIMessage) and not last.tool_calls
        response = (last.text if final else "") or FALLBACK_RESPONSE

        logger.info(
            "agent_run_completed response_chars=%s tool_messages=%s latency_ms=%s",
            len(response),
            len(tool_messages),
            int((perf_counter() - started_at) * 1000),
        )
        return AgentResult(response=response, tool_messages=tool_messages)
