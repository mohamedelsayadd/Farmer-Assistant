import os

# Set at collection time, before any test module imports langfuse, so a developer
# with LANGFUSE_* exported in their shell can never emit real traces from a test run.
os.environ["LANGFUSE_TRACING_ENABLED"] = "False"

import json
from typing import Any

import pytest


class FakeToolCache:
    """In-memory stand-in for memory.tool_cache.ToolCache, keyed like the real one."""

    def __init__(self, cached_results: dict[tuple[str, str], Any] | None = None) -> None:
        self.cached_results = cached_results or {}
        self.stored_results: list[tuple[str, str, dict, Any]] = []

    async def get(self, conversation_id: str, tool_name: str, arguments: dict) -> Any | None:
        return self.cached_results.get((tool_name, json.dumps(arguments, sort_keys=True)))

    async def set(self, conversation_id: str, tool_name: str, arguments: dict, result: Any) -> None:
        self.stored_results.append((conversation_id, tool_name, arguments, result))
        self.cached_results[(tool_name, json.dumps(arguments, sort_keys=True))] = result


@pytest.fixture
def tool_cache() -> FakeToolCache:
    return FakeToolCache()
