import logging

from langfuse import Langfuse

from core.config import Settings

logger = logging.getLogger(__name__)


def create_langfuse_client(settings: Settings) -> Langfuse:
    enabled = bool(settings.langfuse_public_key and settings.langfuse_secret_key)
    if not enabled:
        logger.warning("langfuse_disabled reason=missing_credentials")
    return Langfuse(
        public_key=settings.langfuse_public_key or None,
        secret_key=settings.langfuse_secret_key or None,
        base_url=settings.langfuse_base_url,
        environment=settings.app_env,
        tracing_enabled=enabled,
    )
