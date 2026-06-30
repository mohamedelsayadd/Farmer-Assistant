from core.config import Settings
from providers.STT.interface import SpeechToTextProvider
from providers.STT.providers.faster_whisper import FasterWhisperSpeechToTextProvider


def create_speech_to_text_provider(settings: Settings) -> SpeechToTextProvider:
    provider = settings.stt_provider.lower().strip()
    if provider == "faster_whisper":
        return FasterWhisperSpeechToTextProvider(settings)
    raise ValueError(f"Unsupported STT provider: {settings.stt_provider}")
