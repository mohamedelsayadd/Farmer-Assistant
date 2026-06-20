import json
import logging
from typing import Literal, NotRequired, TypedDict

from redis.asyncio import Redis


Role = Literal["user", "assistant", "tool_context"]
logger = logging.getLogger(__name__)


class MemoryMessage(TypedDict):
    role: Role
    content: str
    tool_name: NotRequired[str]


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
                loaded_message: MemoryMessage = {"role": message["role"], "content": message["content"]}
                if message.get("role") == "tool_context" and isinstance(message.get("tool_name"), str):
                    loaded_message["tool_name"] = message["tool_name"]
                messages.append(loaded_message)
        logger.debug("memory_load_completed conversation_id=%s messages=%s", conversation_id, len(messages))
        return messages

    async def append(self, conversation_id: str, role: Role, content: str) -> None:
        await self._append_payload(conversation_id, {"role": role, "content": content})

    async def append_tool_context(self, conversation_id: str, tool_name: str, content: str) -> None:
        logger.info(
            "memory_tool_context_append_started conversation_id=%s tool_name=%s content_chars=%s",
            conversation_id,
            tool_name,
            len(content),
        )
        await self._append_payload(
            conversation_id,
            {"role": "tool_context", "tool_name": tool_name, "content": content},
        )
        logger.info("memory_tool_context_append_completed conversation_id=%s tool_name=%s", conversation_id, tool_name)

    async def _append_payload(self, conversation_id: str, message: dict[str, str]) -> None:
        key = self._key(conversation_id)
        payload = json.dumps(message, ensure_ascii=False)
        logger.debug(
            "memory_append_started conversation_id=%s role=%s content_chars=%s",
            conversation_id,
            message["role"],
            len(message["content"]),
        )
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.rpush(key, payload)
            pipe.ltrim(key, -self._max_messages, -1)
            pipe.expire(key, self._ttl_seconds)
            await pipe.execute()
        logger.debug(
            "memory_append_completed conversation_id=%s role=%s ttl_seconds=%s max_messages=%s",
            conversation_id,
            message["role"],
            self._ttl_seconds,
            self._max_messages,
        )

    @staticmethod
    def _is_memory_message(message: dict[str, object]) -> bool:
        return message.get("role") in {"user", "assistant", "tool_context"} and isinstance(message.get("content"), str)

    @staticmethod
    def _key(conversation_id: str) -> str:
        return f"conversation:{conversation_id}"
