import logging
from time import perf_counter

from openai import OpenAIError
from redis.exceptions import RedisError

from agent.graph import FarmerAssistantAgent
from memory.redis_memory import RedisMemory
from models.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, memory: RedisMemory, agent: FarmerAssistantAgent) -> None:
        self._memory = memory
        self._agent = agent

    async def chat(self, request: ChatRequest) -> ChatResponse:
        started_at = perf_counter()
        logger.info(
            "chat_request_started conversation_id=%s message_chars=%s",
            request.conversation_id,
            len(request.message),
        )
        try:
            history = await self._memory.load(request.conversation_id)
            logger.info(
                "chat_memory_loaded conversation_id=%s history_messages=%s",
                request.conversation_id,
                len(history),
            )
            assistant_message = await self._agent.run(
                jwt=request.jwt,
                user_message=request.message,
                history=history,
            )
            await self._memory.append(request.conversation_id, "user", request.message)
            await self._memory.append(request.conversation_id, "assistant", assistant_message)
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            logger.info(
                "chat_request_completed conversation_id=%s response_chars=%s latency_ms=%s",
                request.conversation_id,
                len(assistant_message),
                elapsed_ms,
            )
            return ChatResponse(conversation_id=request.conversation_id, message=assistant_message)
        except (OpenAIError, RedisError):
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            logger.exception(
                "chat_request_failed conversation_id=%s latency_ms=%s",
                request.conversation_id,
                elapsed_ms,
            )
            return ChatResponse(
                conversation_id=request.conversation_id,
                message="معلش، حصلت مشكلة مؤقتة. جرّب تاني بعد شوية.",
            )
