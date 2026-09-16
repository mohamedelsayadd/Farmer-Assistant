from langfuse import langfuse 
from core.config import get_settings

langfuse_client = langfuse.Client(
    secret_key=get_settings().langfuse_secret_key,
    public_key=get_settings().langfuse_public_key,
    base_url=get_settings().langfuse_base_url
    )

