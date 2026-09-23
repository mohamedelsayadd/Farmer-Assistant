import logging
from time import perf_counter
from typing import Any

from agents import AgentsException, MaxTurnsExceeded, RunConfig, Runner
from langfuse import get_client, observe, propagate_attributes
from openai import OpenAIError
from redis.exceptions import RedisError

from agent.agent import FALLBACK_RESPONSE, MAX_TOOL_ROUNDS, build_messages, farmer_agent, strip_thinking
from agent.tools import AgentContext
from memory.redis_memory import RedisMemory
from memory.tool_cache import ToolCache
from models.schemas.chat import ChatRequest, ChatResponse
from providers.plant_disease_client import PlantDiseaseClient
from providers.renile_client import ReNileClient

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        memory: RedisMemory,
        renile_client: ReNileClient,
        tool_cache: ToolCache,
        plant_disease_client: PlantDiseaseClient | None = None,
        run_config: RunConfig | None = None,
    ) -> None:
        self._memory = memory
        self._renile_client = renile_client
        self._tool_cache = tool_cache
        self._plant_disease_client = plant_disease_client
        # Tests pass RunConfig(model=...) to swap in a fake model; production uses farmer_agent's own.
        self._run_config = run_config or RunConfig()

    @observe(name="farmer-assistant-chat", capture_input=False)
    async def chat(self, request: ChatRequest) -> ChatResponse:
        started_at = perf_counter()
        logger.info(
            "chat_request_started conversation_id=%s message_chars=%s",
            request.conversation_id,
            len(request.message),
        )
        with propagate_attributes(session_id=request.conversation_id):
            # the request itself is never captured: it carries the jwt and raw image bytes
            get_client().update_current_span(
                input={"message": request.message, "has_image": request.image is not None}
            )
            try:
                history = await self._memory.load(request.conversation_id)
                logger.info(
                    "chat_memory_loaded conversation_id=%s history_messages=%s",
                    request.conversation_id,
                    len(history),
                )
                context = AgentContext(
                    conversation_id=request.conversation_id,
                    jwt=request.jwt,
                    renile_client=self._renile_client,
                    tool_cache=self._tool_cache,
                    plant_disease_client=self._plant_disease_client,
                    image=request.image,
                )
                response = await self.run_agent(context, build_messages(history, request.message, request.image))
                await self._memory.append(request.conversation_id, "user", request.message)
                await self._memory.append(request.conversation_id, "assistant", response)
                elapsed_ms = int((perf_counter() - started_at) * 1000)
                logger.info(
                    "chat_request_completed conversation_id=%s response_chars=%s latency_ms=%s",
                    request.conversation_id,
                    len(response),
                    elapsed_ms,
                )
                return ChatResponse(
                    conversation_id=request.conversation_id,
                    message=response,
                    **plant_disease_metadata(context.plant_prediction),
                )
            except (OpenAIError, AgentsException, RedisError):
                elapsed_ms = int((perf_counter() - started_at) * 1000)
                logger.exception(
                    "chat_request_failed conversation_id=%s latency_ms=%s",
                    request.conversation_id,
                    elapsed_ms,
                )
                get_client().update_current_span(
                    level="ERROR", status_message="chat_request_failed"
                )
                return ChatResponse(
                    conversation_id=request.conversation_id,
                    message="معلش، حصلت مشكلة مؤقتة. جرّب تاني بعد شوية.",
                )

    async def run_agent(self, context: AgentContext, messages: list[Any]) -> str:
        try:
            # MAX_TOOL_ROUNDS tool rounds plus the model call that answers from them.
            result = await Runner.run(
                farmer_agent,
                messages,
                context=context,
                run_config=self._run_config,
                max_turns=MAX_TOOL_ROUNDS + 1,
            )
        except MaxTurnsExceeded:
            logger.warning("agent_tool_round_limit_reached max_rounds=%s", MAX_TOOL_ROUNDS)
            return FALLBACK_RESPONSE
        return strip_thinking(result.final_output) or FALLBACK_RESPONSE


def plant_disease_metadata(prediction: dict[str, Any] | None) -> dict[str, str | None]:
    prediction = prediction or {}
    source = prediction.get("source")
    disease = prediction.get("disease")
    return {
        "source": source if isinstance(source, str) and source else None,
        "disease": disease if isinstance(disease, str) and disease else None,
    }
