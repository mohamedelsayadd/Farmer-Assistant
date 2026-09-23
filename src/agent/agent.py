from datetime import date
from typing import Any

from agents import Agent, ModelSettings, OpenAIChatCompletionsModel, RunContextWrapper, TResponseInputItem
from openai import AsyncOpenAI

from agent.prompts import SYSTEM_PROMPT
from agent.tools import TOOLS, AgentContext
from core.config import get_settings
from memory.redis_memory import MemoryMessage
from models.schemas.chat import UploadedImage

IMAGE_ATTACHMENT_MARKER = "[The user attached a plant image with this message.]"
MAX_TOOL_ROUNDS = 4
FALLBACK_RESPONSE = "معلش، مش قادر أوصل لإجابة واضحة دلوقتي."

settings = get_settings()

# OpenAI-compatible chat model (vLLM/Qwen) over the Chat Completions API.
client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)
model = OpenAIChatCompletionsModel(model=settings.llm_model, openai_client=client)
model_settings = ModelSettings(
    temperature=settings.llm_temperature,
    max_tokens=settings.llm_max_tokens,
    top_p=settings.llm_top_p,
    extra_body={
        "top_k": settings.llm_top_k,
        "chat_template_kwargs": {"enable_thinking": settings.llm_enable_thinking},
    },
)


def system_prompt() -> str:
    # Rebuilt per request so relative Arabic dates ("امبارح", "آخر أسبوع") resolve against today.
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"تاريخ النهاردة: {date.today().isoformat()}. استخدم التاريخ ده عشان تفهم عبارات زي امبارح، "
        "آخر أسبوع، آخر 3 أسابيع، آخر فترة، من يومين، يوم الأحد اللي فات، ومن شهر 1 لشهر 5."
    )


def instructions(ctx: RunContextWrapper[AgentContext], agent: Agent[AgentContext]) -> str:
    return system_prompt()


farmer_agent = Agent[AgentContext](
    name="Farmer Assistant",
    instructions=instructions,
    tools=TOOLS,
    model=model,
    model_settings=model_settings,
)


def build_messages(
    history: list[MemoryMessage],
    user_message: str,
    image: UploadedImage | None = None,
) -> list[TResponseInputItem]:
    messages: list[TResponseInputItem] = [{"role": item["role"], "content": item["content"]} for item in history]
    if image is not None:
        user_message = f"{user_message}\n\n{IMAGE_ATTACHMENT_MARKER}"
    messages.append({"role": "user", "content": user_message})
    return messages


def strip_thinking(content: Any) -> Any:
    if not isinstance(content, str) or "</think>" not in content:
        return content
    return content.rsplit("</think>", maxsplit=1)[-1].strip()
