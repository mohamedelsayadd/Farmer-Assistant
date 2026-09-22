from core.config import Settings
from providers.ASR.interface import ASRProvider
from providers.ASR.providers.cohere import CohereASRProvider
from providers.ASR.providers.faster_whisper import FasterWhisperASRProvider
from providers.ASR.providers.fms_voice import FMSVoiceASRProvider


def create_asr_provider(settings: Settings) -> ASRProvider:
    provider = settings.asr_provider.lower().strip()
    if provider == "fms_voice":
        return FMSVoiceASRProvider(settings)
    if provider == "cohere":
        return CohereASRProvider(settings)
    if provider == "faster_whisper":
        return FasterWhisperASRProvider(settings)
    raise ValueError(f"Unsupported ASR provider: {settings.asr_provider}")
