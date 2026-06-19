from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from redis.asyncio import Redis

from agent.graph import FarmerAssistantAgent
from api.v1.endpoints.chat import router as chat_router
from core.config import get_settings
from core.logging import configure_logging
from memory.redis_memory import RedisMemory
from providers.llm import LLMProvider
from services.chat_service import ChatService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)

    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    await redis.ping()

    memory = RedisMemory(
        redis=redis,
        ttl_seconds=settings.redis_memory_ttl_seconds,
        max_messages=settings.redis_memory_max_messages,
    )
    llm = LLMProvider(settings)
    app.state.redis = redis
    app.state.chat_service = ChatService(memory=memory, agent=FarmerAssistantAgent(llm))

    try:
        yield
    finally:
        await redis.aclose()


app = FastAPI(title="ReNile Farmer Assistant", lifespan=lifespan)
app.include_router(chat_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
