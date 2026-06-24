import json

import pytest

from memory.redis_memory import RedisMemory


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self._redis = redis
        self._commands: list[tuple[str, tuple[object, ...]]] = []

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def rpush(self, key: str, value: str) -> None:
        self._commands.append(("rpush", (key, value)))

    def ltrim(self, key: str, start: int, end: int) -> None:
        self._commands.append(("ltrim", (key, start, end)))

    def expire(self, key: str, ttl: int) -> None:
        self._commands.append(("expire", (key, ttl)))

    async def execute(self) -> None:
        for command, args in self._commands:
            if command == "rpush":
                key, value = args
                self._redis.data.setdefault(key, []).append(value)
            elif command == "ltrim":
                key, start, end = args
                values = self._redis.data.get(key, [])
                self._redis.data[key] = values[start : end + 1 if end != -1 else None]
            elif command == "expire":
                key, ttl = args
                self._redis.ttls[key] = ttl


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, list[str]] = {}
        self.ttls: dict[str, int] = {}

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        values = self.data.get(key, [])
        return values[start : end + 1 if end != -1 else None]

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        assert transaction is True
        return FakePipeline(self)


@pytest.mark.asyncio
async def test_memory_trims_to_max_messages_and_sets_ttl() -> None:
    redis = FakeRedis()
    memory = RedisMemory(redis=redis, ttl_seconds=3600, max_messages=12)  # type: ignore[arg-type]

    for index in range(20):
        await memory.append("conversation-1", "user", f"message-{index}")

    messages = await memory.load("conversation-1")


    assert len(messages) == 12
    assert messages[0]["content"] == "message-8"
    assert redis.ttls["conversation:conversation-1"] == 3600


@pytest.mark.asyncio
async def test_memory_does_not_store_jwt() -> None:
    redis = FakeRedis()
    memory = RedisMemory(redis=redis, ttl_seconds=3600, max_messages=12)  # type: ignore[arg-type]

    await memory.append("conversation-1", "user", "درجة الحرارة كام؟")

    stored_payload = json.dumps(redis.data, ensure_ascii=False)

    assert "secret-jwt" not in stored_payload


@pytest.mark.asyncio
async def test_memory_ignores_legacy_tool_context_messages() -> None:
    redis = FakeRedis()
    memory = RedisMemory(redis=redis, ttl_seconds=3600, max_messages=12)  # type: ignore[arg-type]
    redis.data["conversation:conversation-1"] = [
        json.dumps(
            {"role": "tool_context", "tool_name": "get_current_readings", "content": '{"devices": []}'},
            ensure_ascii=False,
        )
    ]

    messages = await memory.load("conversation-1")

    assert messages == []
