import json
import logging
from typing import Literal, NotRequired, TypedDict

from redis.asyncio import Redis


Role = Literal["user", "assistant"]
logger = logging.getLogger(__name__)


class MemoryMessage(TypedDict):
    role: Role
    content: str
    # Name of the agent that wrote an assistant turn; the next request starts at that agent.
    agent: NotRequired[str]


class RedisMemory:
    def __init__(self, redis: Redis, ttl_seconds: int, max_messages: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds
        self._max_messages = max_messages

    async def load(self, conversation_id: str) -> list[MemoryMessage]:
        logger.debug("memory_load_started conversation_id=%s", conversation_id)
        raw_messages = await self._redis.lrange(self._key(conversation_id), 0, -1)
        messages: list[MemoryMessage] = []
        for raw_message in raw_messages:
            value = raw_message.decode("utf-8") if isinstance(raw_message, bytes) else raw_message
            message = json.loads(value)
            if self._is_memory_message(message):
                item: MemoryMessage = {"role": message["role"], "content": message["content"]}
                if isinstance(message.get("agent"), str):
                    item["agent"] = message["agent"]
                messages.append(item)
        logger.debug("memory_load_completed conversation_id=%s messages=%s", conversation_id, len(messages))
        return messages

    async def append(self, conversation_id: str, role: Role, content: str, agent: str | None = None) -> None:
        key = self._key(conversation_id)
        message: MemoryMessage = {"role": role, "content": content}
        if agent is not None:
            message["agent"] = agent
        payload = json.dumps(message, ensure_ascii=False)
        logger.debug(
            "memory_append_started conversation_id=%s role=%s content_chars=%s",
            conversation_id,
            role,
            len(content),
        )
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.rpush(key, payload)
            pipe.ltrim(key, -self._max_messages, -1)
            pipe.expire(key, self._ttl_seconds)
            await pipe.execute()
        logger.debug(
            "memory_append_completed conversation_id=%s role=%s ttl_seconds=%s max_messages=%s",
            conversation_id,
            role,
            self._ttl_seconds,
            self._max_messages,
        )

    @staticmethod
    def _is_memory_message(message: dict[str, object]) -> bool:
        return message.get("role") in {"user", "assistant"} and isinstance(message.get("content"), str)

    @staticmethod
    def _key(conversation_id: str) -> str:
        return f"conversation:{conversation_id}"
