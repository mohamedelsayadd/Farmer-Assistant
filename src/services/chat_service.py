import logging

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
        try:
            history = await self._memory.load(request.conversation_id)
            assistant_message = await self._agent.run(
                jwt=request.jwt,
                user_message=request.message,
                history=history,
            )
            await self._memory.append(request.conversation_id, "user", request.message)
            await self._memory.append(request.conversation_id, "assistant", assistant_message)
            return ChatResponse(conversation_id=request.conversation_id, message=assistant_message)
        except (OpenAIError, RedisError):
            logger.exception("Chat request failed", extra={"conversation_id": request.conversation_id})
            return ChatResponse(
                conversation_id=request.conversation_id,
                message="معلش، حصلت مشكلة مؤقتة. جرّب تاني بعد شوية.",
            )
