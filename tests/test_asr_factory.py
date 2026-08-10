import pytest

from core.config import Settings
from providers.ASR.factory import create_asr_provider
from providers.ASR.providers.cohere import CohereASRProvider, resolve_torch_dtype
from providers.ASR.providers.faster_whisper import FasterWhisperASRProvider

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
    "HTTP_TIMEOUT_SECONDS": "40",
    "ASR_PROVIDER": "cohere",
    "ASR_MODEL": "CohereLabs/cohere-transcribe-arabic-07-2026",
    "ASR_DEVICE": "cpu",
    "ASR_LANGUAGE": "ar",
    "ASR_MAX_AUDIO_BYTES": "524288",
    "ASR_COMPUTE_TYPE": "int8",
    "ASR_DTYPE": "float16",
    "ASR_MAX_NEW_TOKENS": "256",
    "TTS_PROVIDER": "voicetut",
    "TTS_MODEL": "mohammedaly22/VoiceTut-TTS",
    "TTS_DEVICE": "cpu",
    "TTS_DTYPE": "float16",
    "TTS_SPEAKER": "Asmaa",
    "TTS_NUM_STEP": "48",
    "TTS_GUIDANCE_SCALE": "2.5",
    "TTS_SPEED": "1.05",
}


def build_settings(**overrides: str) -> Settings:
    # Init values outrank the .env file, so this never depends on a local .env.
    return Settings(**{**BASE_ENV, **overrides})


def test_factory_returns_cohere_provider() -> None:
    provider = create_asr_provider(build_settings(ASR_PROVIDER="cohere"))

    assert isinstance(provider, CohereASRProvider)


def test_factory_returns_faster_whisper_provider() -> None:
    provider = create_asr_provider(build_settings(ASR_PROVIDER="faster_whisper"))

    assert isinstance(provider, FasterWhisperASRProvider)


def test_factory_ignores_provider_case_and_whitespace() -> None:
    provider = create_asr_provider(build_settings(ASR_PROVIDER="  FASTER_WHISPER "))

    assert isinstance(provider, FasterWhisperASRProvider)


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported ASR provider: whisper"):
        create_asr_provider(build_settings(ASR_PROVIDER="whisper"))


def test_cohere_provider_requires_a_language() -> None:
    # The Cohere processor builds its decoder prompt from the language code and
    # has no auto-detection mode, unlike faster-whisper.
    with pytest.raises(ValueError, match="ASR_LANGUAGE is required"):
        create_asr_provider(build_settings(ASR_PROVIDER="cohere", ASR_LANGUAGE=""))


def test_faster_whisper_provider_allows_empty_language() -> None:
    provider = create_asr_provider(build_settings(ASR_PROVIDER="faster_whisper", ASR_LANGUAGE=""))

    assert isinstance(provider, FasterWhisperASRProvider)
    assert provider._language is None


def test_cohere_provider_rejects_unknown_dtype() -> None:
    with pytest.raises(ValueError, match="Unsupported ASR_DTYPE: int8"):
        create_asr_provider(build_settings(ASR_PROVIDER="cohere", ASR_DTYPE="int8"))


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("float16", "float16"), ("FP16", "float16"), ("bfloat16", "bfloat16"), ("float32", "float32")],
)
def test_resolve_torch_dtype(configured: str, expected: str) -> None:
    import torch

    assert resolve_torch_dtype(configured) is getattr(torch, expected)
