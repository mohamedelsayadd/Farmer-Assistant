import os

# Set at collection time, before any test module imports langfuse, so a developer
# with LANGFUSE_* exported in their shell can never emit real traces from a test run.
os.environ["LANGFUSE_TRACING_ENABLED"] = "False"

import json
from typing import Any

import pytest

from core.config import Settings


BASE_ENV = {
    "APP_NAME": "test",
    "APP_ENV": "test",
    "LOG_LEVEL": "INFO",
    "LLM_API_KEY": "EMPTY",
    "LLM_BASE_URL": "http://localhost:5000/v1",
    "LLM_MODEL": "test-model",
    "LLM_ENABLE_THINKING": "false",
    "LLM_TEMPERATURE": "0.2",
    "LLM_MAX_TOKENS": "1024",
    "LLM_TOP_P": "0.8",
    "LLM_TOP_K": "20",
    "REDIS_URL": "redis://localhost:6379/0",
    "REDIS_MEMORY_TTL_SECONDS": "3600",
    "REDIS_MEMORY_MAX_MESSAGES": "12",
    "REDIS_TOOL_CACHE_URL": "redis://localhost:6379/1",
    "REDIS_TOOL_CACHE_TTL_SECONDS": "600",
    "RENILE_API_BASE_URL": "https://renile-iot.com",
    "RENILE_DEVICES_PATH": "/api/v1/devices/names/",
    "RENILE_CURRENT_READINGS_PATH": "/api/v1/snapshot",
    "RENILE_HISTORICAL_READINGS_PATH": "/api/v1/data/",
    "PLANT_DISEASE_API_BASE_URL": "http://127.0.0.1:8002",
    "PLANT_DISEASE_PREDICT_PATH": "/api/v1/predict",
    "PLANT_DISEASE_MAX_IMAGE_BYTES": "5242880",
    "HTTP_TIMEOUT_SECONDS": "40",
    "ASR_PROVIDER": "fms_voice",
    "ASR_LANGUAGE": "ar",
    "ASR_MAX_AUDIO_BYTES": "524288",
    "ASR_REMOTE_BASE_URL": "http://asr.test",
    "ASR_REMOTE_TRANSCRIBE_PATH": "/transcribe",
    "ASR_REMOTE_TIMEOUT_SECONDS": "120",
    "LANGFUSE_SECRET_KEY": "sk-lf-test",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
    "LANGFUSE_BASE_URL": "https://cloud.langfuse.com",
}


# agent.agent builds its model from get_settings() at import time; seed the process env so
# that never depends on a local .env (env vars outrank the .env file).
os.environ.update(BASE_ENV)


def build_settings(**overrides: str) -> Settings:
    # Init values outrank the .env file, so this never depends on a local .env.
    return Settings(**{**BASE_ENV, **overrides})


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
