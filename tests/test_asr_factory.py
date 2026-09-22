import pytest

from conftest import build_settings
from providers.ASR.factory import create_asr_provider
from providers.ASR.providers.cohere import CohereASRProvider, resolve_torch_dtype
from providers.ASR.providers.faster_whisper import FasterWhisperASRProvider
from providers.ASR.providers.fms_voice import FMSVoiceASRProvider


def test_factory_returns_fms_voice_provider() -> None:
    provider = create_asr_provider(build_settings(ASR_PROVIDER="fms_voice"))

    assert isinstance(provider, FMSVoiceASRProvider)


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


def test_fms_voice_provider_rejects_unsupported_language() -> None:
    # The service accepts ar and en only; fail at startup rather than per request.
    with pytest.raises(ValueError, match="Unsupported ASR_LANGUAGE for the fms_voice provider: fr"):
        create_asr_provider(build_settings(ASR_PROVIDER="fms_voice", ASR_LANGUAGE="fr"))
