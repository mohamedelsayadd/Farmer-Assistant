import logging

from langfuse import Langfuse
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor

from core.config import Settings

logger = logging.getLogger(__name__)


def create_langfuse_client(settings: Settings) -> Langfuse:
    enabled = bool(settings.langfuse_public_key and settings.langfuse_secret_key)
    if not enabled:
        logger.warning("langfuse_disabled reason=missing_credentials")
    client = Langfuse(
        public_key=settings.langfuse_public_key or None,
        secret_key=settings.langfuse_secret_key or None,
        base_url=settings.langfuse_base_url,
        environment=settings.app_env,
        tracing_enabled=enabled,
    )
    # Routes Agents SDK spans (model calls, tools) into Langfuse under the @observe root span.
    # It also replaces the SDK's default trace exporter, which would otherwise send to OpenAI.
    OpenAIAgentsInstrumentor().instrument()
    return client
