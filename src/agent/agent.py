import logging
from dataclasses import dataclass
from datetime import date
from time import perf_counter
from typing import Any

from agents import (
    Agent,
    MaxTurnsExceeded,
    Model,
    ModelSettings,
    RunContextWrapper,
    Runner,
    ToolCallItem,
    ToolCallOutputItem,
    TResponseInputItem,
)

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


@dataclass(frozen=True)
class ToolOutput:
    name: str
    output: str


@dataclass(frozen=True)
class AgentResult:
    response: str
    tool_outputs: list[ToolOutput]


def system_prompt() -> str:
    # Rebuilt per request so relative Arabic dates ("امبارح", "آخر أسبوع") resolve against today.
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"تاريخ النهاردة: {date.today().isoformat()}. استخدم التاريخ ده عشان تفهم عبارات زي امبارح، "
        "آخر أسبوع، آخر 3 أسابيع، آخر فترة، من يومين، يوم الأحد اللي فات، ومن شهر 1 لشهر 5."
    )


def _instructions(ctx: RunContextWrapper[AgentContext], agent: Agent[AgentContext]) -> str:
    return system_prompt()


def build_messages(
    history: list[MemoryMessage],
    user_message: str,
    image: UploadedImage | None = None,
) -> list[TResponseInputItem]:
    messages: list[TResponseInputItem] = [{"role": item["role"], "content": item["content"]} for item in history]
    if image is not None:
        user_message = f"{user_message}\n\n{IMAGE_ATTACHMENT_MARKER}"
    messages.append({"role": "user", "content": user_message})
    return messages


def strip_thinking(content: Any) -> Any:
    if not isinstance(content, str) or "</think>" not in content:
        return content
    return content.rsplit("</think>", maxsplit=1)[-1].strip()


class FarmerAssistantAgent:
    def __init__(
        self,
        model: Model,
        model_settings: ModelSettings,
        renile_client: ReNileClient,
        tool_cache: ToolCache,
        plant_disease_client: PlantDiseaseClient | None = None,
    ) -> None:
        self._renile_client = renile_client
        self._tool_cache = tool_cache
        self._plant_disease_client = plant_disease_client
        self._agent = Agent[AgentContext](
            name="farmer-assistant",
            instructions=_instructions,
            tools=TOOLS,
            model=model,
            model_settings=model_settings,
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
        context = AgentContext(
            conversation_id=conversation_id,
            jwt=jwt,
            renile_client=self._renile_client,
            tool_cache=self._tool_cache,
            plant_disease_client=self._plant_disease_client,
            image=image,
        )
        try:
            # MAX_TOOL_ROUNDS tool rounds plus the model call that answers from them.
            result = await Runner.run(
                self._agent,
                build_messages(history, user_message, image),
                context=context,
                max_turns=MAX_TOOL_ROUNDS + 1,
            )
        except MaxTurnsExceeded:
            logger.warning("agent_tool_round_limit_reached max_rounds=%s", MAX_TOOL_ROUNDS)
            return AgentResult(response=FALLBACK_RESPONSE, tool_outputs=[])

        tool_outputs = collect_tool_outputs(result.new_items)
        response = strip_thinking(result.final_output) or FALLBACK_RESPONSE

        logger.info(
            "agent_run_completed response_chars=%s tool_messages=%s latency_ms=%s",
            len(response),
            len(tool_outputs),
            int((perf_counter() - started_at) * 1000),
        )
        return AgentResult(response=response, tool_outputs=tool_outputs)


def collect_tool_outputs(items: list[Any]) -> list[ToolOutput]:
    # Output items carry only the call_id; the tool name lives on the matching call item.
    names = {item.raw_item.call_id: item.raw_item.name for item in items if isinstance(item, ToolCallItem)}
    return [
        ToolOutput(name=names.get(item.raw_item["call_id"], ""), output=str(item.output))
        for item in items
        if isinstance(item, ToolCallOutputItem)
    ]
