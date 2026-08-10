from core.config import Settings
from providers.ASR.interface import ASRProvider
from providers.ASR.providers.cohere import CohereASRProvider
from providers.ASR.providers.faster_whisper import FasterWhisperASRProvider


def create_asr_provider(settings: Settings) -> ASRProvider:
    provider = settings.asr_provider.lower().strip()
    if provider == "cohere":
        return CohereASRProvider(settings)
    if provider == "faster_whisper":
        return FasterWhisperASRProvider(settings)
    raise ValueError(f"Unsupported ASR provider: {settings.asr_provider}")
