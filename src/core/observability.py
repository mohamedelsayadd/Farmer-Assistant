import logging

from agents import set_tracing_disabled
from langfuse import Langfuse
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor

from core.config import Settings

logger = logging.getLogger(__name__)


def create_langfuse_client(settings: Settings) -> Langfuse:
    has_credentials = bool(settings.langfuse_public_key and settings.langfuse_secret_key)
    enabled = settings.langfuse_observe and has_credentials
    if not settings.langfuse_observe:
        logger.info("langfuse_disabled reason=observe_flag_off")
    elif not has_credentials:
        logger.warning("langfuse_disabled reason=missing_credentials")
    client = Langfuse(
        public_key=settings.langfuse_public_key or None,
        secret_key=settings.langfuse_secret_key or None,
        base_url=settings.langfuse_base_url,
        environment=settings.app_env,
        tracing_enabled=enabled,
    )
    if enabled:
        # Routes Agents SDK spans (model calls, tools) into Langfuse under the @observe root span.
        # It also replaces the SDK's default trace exporter, which would otherwise send to OpenAI.
        OpenAIAgentsInstrumentor().instrument()
    else:
        # Without the instrumentor the SDK's default exporter would send traces to OpenAI.
        set_tracing_disabled(True)
    return client
