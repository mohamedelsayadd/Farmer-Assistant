import pytest

from conftest import build_settings
from providers.ASR.factory import create_asr_provider
from providers.ASR.providers.fms_voice import FMSVoiceASRProvider


def test_factory_returns_fms_voice_provider() -> None:
    provider = create_asr_provider(build_settings(ASR_PROVIDER="fms_voice"))

    assert isinstance(provider, FMSVoiceASRProvider)


def test_factory_ignores_provider_case_and_whitespace() -> None:
    provider = create_asr_provider(build_settings(ASR_PROVIDER="  FMS_VOICE "))

    assert isinstance(provider, FMSVoiceASRProvider)


@pytest.mark.parametrize("provider", ["cohere", "faster_whisper", "whisper"])
def test_factory_rejects_unknown_provider(provider: str) -> None:
    with pytest.raises(ValueError, match=f"Unsupported ASR provider: {provider}"):
        create_asr_provider(build_settings(ASR_PROVIDER=provider))


def test_fms_voice_provider_rejects_unsupported_language() -> None:
    # The service accepts ar and en only; fail at startup rather than per request.
    with pytest.raises(ValueError, match="Unsupported ASR_LANGUAGE for the fms_voice provider: fr"):
        create_asr_provider(build_settings(ASR_PROVIDER="fms_voice", ASR_LANGUAGE="fr"))
