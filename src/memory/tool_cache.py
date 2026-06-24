import hashlib
import json
import logging
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class ToolCache:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def get(self, conversation_id: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        key = self._key(conversation_id, tool_name, arguments)
        raw_value = await self._redis.get(key)
        if raw_value is None:
            logger.info("tool_cache_miss conversation_id=%s tool_name=%s", conversation_id, tool_name)
            return None

        value = raw_value.decode("utf-8") if isinstance(raw_value, bytes) else raw_value
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            logger.warning("tool_cache_invalid_json conversation_id=%s tool_name=%s", conversation_id, tool_name)
            return None

        content = payload.get("content")
        if not isinstance(content, str):
            logger.warning("tool_cache_invalid_content conversation_id=%s tool_name=%s", conversation_id, tool_name)
            return None

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("tool_cache_invalid_result_json conversation_id=%s tool_name=%s", conversation_id, tool_name)
            return None

        if not isinstance(result, dict):
            logger.warning("tool_cache_invalid_result_type conversation_id=%s tool_name=%s", conversation_id, tool_name)
            return None

        logger.info("tool_cache_hit conversation_id=%s tool_name=%s", conversation_id, tool_name)
        return result

    async def set(self, conversation_id: str, tool_name: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
        key = self._key(conversation_id, tool_name, arguments)
        content = json.dumps(result, ensure_ascii=False)
        payload = json.dumps(
            {
                "tool_name": tool_name,
                "arguments": arguments,
                "content": content,
            },
            ensure_ascii=False,
        )
        await self._redis.setex(key, self._ttl_seconds, payload)
        logger.info(
            "tool_cache_set conversation_id=%s tool_name=%s content_chars=%s ttl_seconds=%s",
            conversation_id,
            tool_name,
            len(content),
            self._ttl_seconds,
        )

    @classmethod
    def _key(cls, conversation_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
        return f"tool_cache:{conversation_id}:{tool_name}:{cls._arguments_hash(arguments)}"

    @staticmethod
    def _arguments_hash(arguments: dict[str, Any]) -> str:
        normalized_arguments = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized_arguments.encode("utf-8")).hexdigest()
