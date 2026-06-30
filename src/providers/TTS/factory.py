from core.config import Settings
from providers.TTS.interface import TextToSpeechProvider
from providers.TTS.providers.voicetut import VoiceTutTextToSpeechProvider


def create_text_to_speech_provider(settings: Settings) -> TextToSpeechProvider:
    provider = settings.tts_provider.lower().strip()
    if provider == "voicetut":
        return VoiceTutTextToSpeechProvider(settings)
    raise ValueError(f"Unsupported TTS provider: {settings.tts_provider}")
