import json

import pytest

from memory.tool_cache import ToolCache


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.data[key] = value
        self.ttls[key] = ttl


@pytest.mark.asyncio
async def test_tool_cache_stores_and_loads_processed_result() -> None:
    redis = FakeRedis()
    cache = ToolCache(redis=redis, ttl_seconds=3600)  # type: ignore[arg-type]

    await cache.set(
        conversation_id="conversation-1",
        tool_name="get_last_duration_summary",
        arguments={"start_time": "2026-06-01 00:00", "device_id": "device-1"},
        result={"daily_rows": []},
    )

    result = await cache.get(
        conversation_id="conversation-1",
        tool_name="get_last_duration_summary",
        arguments={"device_id": "device-1", "start_time": "2026-06-01 00:00"},
    )

    assert result == {"daily_rows": []}
    assert list(redis.ttls.values()) == [3600]


@pytest.mark.asyncio
async def test_tool_cache_stores_and_loads_list_result() -> None:
    redis = FakeRedis()
    cache = ToolCache(redis=redis, ttl_seconds=3600)  # type: ignore[arg-type]
    devices = [{"_id": "device-1", "name": "Device 1"}]

    await cache.set(
        conversation_id="conversation-1",
        tool_name="get_devices_ids",
        arguments={},
        result=devices,
    )

    result = await cache.get(
        conversation_id="conversation-1",
        tool_name="get_devices_ids",
        arguments={},
    )

    assert result == devices


@pytest.mark.asyncio
async def test_tool_cache_key_includes_arguments_hash() -> None:
    redis = FakeRedis()
    cache = ToolCache(redis=redis, ttl_seconds=3600)  # type: ignore[arg-type]

    await cache.set("conversation-1", "get_specific_time_readings", {"device_id": "device-1"}, {"hourly_rows": [1]})

    result = await cache.get("conversation-1", "get_specific_time_readings", {"device_id": "device-2"})

    assert result is None


@pytest.mark.asyncio
async def test_tool_cache_returns_none_for_invalid_payload() -> None:
    redis = FakeRedis()
    cache = ToolCache(redis=redis, ttl_seconds=3600)  # type: ignore[arg-type]
    key = ToolCache._key("conversation-1", "get_current_readings", {})  # noqa: SLF001
    redis.data[key] = json.dumps({"content": "not-json"})

    result = await cache.get("conversation-1", "get_current_readings", {})

    assert result is None
