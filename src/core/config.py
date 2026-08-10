from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    `.env` is the single source of truth: every field below is required and has
    no in-code default, so a missing key fails fast at startup instead of
    silently falling back to a value hidden in this file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(alias="APP_NAME")
    app_env: str = Field(alias="APP_ENV")
    log_level: str = Field(alias="LOG_LEVEL")

    llm_api_key: str = Field(alias="LLM_API_KEY")
    llm_base_url: str = Field(alias="LLM_BASE_URL")
    llm_model: str = Field(alias="LLM_MODEL")
    llm_enable_thinking: bool = Field(alias="LLM_ENABLE_THINKING")
    llm_temperature: float = Field(alias="LLM_TEMPERATURE", ge=0, le=2)
    llm_max_tokens: int = Field(alias="LLM_MAX_TOKENS", gt=0)
    llm_top_p: float = Field(alias="LLM_TOP_P", gt=0, le=1)
    llm_top_k: int = Field(alias="LLM_TOP_K", gt=0)

    redis_url: str = Field(alias="REDIS_URL")
    redis_memory_ttl_seconds: int = Field(alias="REDIS_MEMORY_TTL_SECONDS", gt=0)
    redis_memory_max_messages: int = Field(alias="REDIS_MEMORY_MAX_MESSAGES", gt=0)
    redis_tool_cache_url: str = Field(alias="REDIS_TOOL_CACHE_URL")
    redis_tool_cache_ttl_seconds: int = Field(alias="REDIS_TOOL_CACHE_TTL_SECONDS", gt=0)

    renile_api_base_url: str = Field(alias="RENILE_API_BASE_URL")
    renile_devices_path: str = Field(alias="RENILE_DEVICES_PATH")
    renile_current_readings_path: str = Field(alias="RENILE_CURRENT_READINGS_PATH")
    renile_historical_readings_path: str = Field(alias="RENILE_HISTORICAL_READINGS_PATH")

    http_timeout_seconds: float = Field(alias="HTTP_TIMEOUT_SECONDS", gt=0)

    asr_provider: str = Field(alias="ASR_PROVIDER")
    asr_model: str = Field(alias="ASR_MODEL")
    asr_device: str = Field(alias="ASR_DEVICE")
    asr_language: str | None = Field(alias="ASR_LANGUAGE")
    asr_max_audio_bytes: int = Field(alias="ASR_MAX_AUDIO_BYTES", gt=0)
    asr_compute_type: str = Field(alias="ASR_COMPUTE_TYPE")
    asr_dtype: str = Field(alias="ASR_DTYPE")
    asr_max_new_tokens: int = Field(alias="ASR_MAX_NEW_TOKENS", gt=0)

    tts_provider: str = Field(alias="TTS_PROVIDER")
    tts_model: str = Field(alias="TTS_MODEL")
    tts_device: str = Field(alias="TTS_DEVICE")
    tts_dtype: str = Field(alias="TTS_DTYPE")
    tts_speaker: str = Field(alias="TTS_SPEAKER")
    tts_num_step: int = Field(alias="TTS_NUM_STEP", gt=0)
    tts_guidance_scale: float = Field(alias="TTS_GUIDANCE_SCALE", gt=0)
    tts_speed: float = Field(alias="TTS_SPEED", gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
