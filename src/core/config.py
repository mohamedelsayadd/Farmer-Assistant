from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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
    llm_enable_thinking: bool = Field(default=False, alias="LLM_ENABLE_THINKING")
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE", ge=0, le=2)
    llm_max_tokens: int = Field(default=1024, alias="LLM_MAX_TOKENS", gt=0)
    llm_top_p: float = Field(default=0.8, alias="LLM_TOP_P", gt=0, le=1)
    llm_top_k: int = Field(default=20, alias="LLM_TOP_K", gt=0)

    redis_url: str = Field(alias="REDIS_URL")
    redis_memory_ttl_seconds: int = Field(alias="REDIS_MEMORY_TTL_SECONDS", gt=0)
    redis_memory_max_messages: int = Field(alias="REDIS_MEMORY_MAX_MESSAGES", gt=0)
    redis_tool_cache_url: str = Field(default="redis://localhost:6379/1", alias="REDIS_TOOL_CACHE_URL")
    redis_tool_cache_ttl_seconds: int = Field(default=3600, alias="REDIS_TOOL_CACHE_TTL_SECONDS", gt=0)

    renile_api_base_url: str = Field(alias="RENILE_API_BASE_URL")
    renile_current_readings_path: str = Field(alias="RENILE_CURRENT_READINGS_PATH")
    renile_historical_readings_path: str = Field(alias="RENILE_HISTORICAL_READINGS_PATH")

    http_timeout_seconds: float = Field(alias="HTTP_TIMEOUT_SECONDS", gt=0)

    stt_model: str = Field(default="Systran/faster-whisper-large-v3", alias="STT_MODEL")
    stt_device: str = Field(default="cpu", alias="STT_DEVICE")
    stt_compute_type: str = Field(default="int8", alias="STT_COMPUTE_TYPE")
    stt_language: str | None = Field(default="ar", alias="STT_LANGUAGE")
    stt_max_audio_bytes: int = Field(default=10 * 1024 * 1024, alias="STT_MAX_AUDIO_BYTES", gt=0)

    tts_model: str = Field(default="k2-fsa/OmniVoice", alias="TTS_MODEL")
    tts_device_map: str = Field(default="cuda:0", alias="TTS_DEVICE_MAP")
    tts_dtype: str = Field(default="float16", alias="TTS_DTYPE")
    tts_sample_rate: int = Field(default=24000, alias="TTS_SAMPLE_RATE", gt=0)
    tts_reference_audio_path: str = Field(default="./3.wav", alias="TTS_REFERENCE_AUDIO_PATH")


@lru_cache
def get_settings() -> Settings:
    return Settings()
