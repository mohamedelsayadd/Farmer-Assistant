import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from redis.asyncio import Redis

from agent.graph import FarmerAssistantAgent
from api.v1.endpoints.chat import router as chat_router
from core.config import get_settings
from core.logging import configure_logging
from memory.redis_memory import RedisMemory
from memory.tool_cache import ToolCache
from providers.ASR.factory import create_asr_provider
from providers.TTS.factory import create_text_to_speech_provider
from providers.llm import LLMProvider
from providers.renile_client import ReNileClient
from services.chat_service import ChatService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)

    # prepare redis clients
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    tool_cache_redis = Redis.from_url(settings.redis_tool_cache_url, decode_responses=False)
    # connect to redis and check if it's alive
    await redis.ping()
    await tool_cache_redis.ping()

    memory = RedisMemory(
        redis=redis,
        ttl_seconds=settings.redis_memory_ttl_seconds,
        max_messages=settings.redis_memory_max_messages,
    )
    llm = LLMProvider(settings)
    renile_client = ReNileClient(settings)
    asr = create_asr_provider(settings)
    text_to_speech = create_text_to_speech_provider(settings)
    await asr.load_model()
   #await asyncio.gather(asr.load_model(), text_to_speech.load_model())

    app.state.redis = redis
    app.state.tool_cache_redis = tool_cache_redis
    app.state.asr = asr
    app.state.text_to_speech = text_to_speech
    app.state.asr_max_audio_bytes = settings.asr_max_audio_bytes
    tool_cache = ToolCache(redis=tool_cache_redis, ttl_seconds=settings.redis_tool_cache_ttl_seconds)
    app.state.chat_service = ChatService(memory=memory, agent=FarmerAssistantAgent(llm, renile_client, tool_cache))

    try:
        yield
    finally:
        await redis.aclose()
        await tool_cache_redis.aclose()


app = FastAPI(title="ReNile Farmer Assistant", lifespan=lifespan)
app.include_router(chat_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
