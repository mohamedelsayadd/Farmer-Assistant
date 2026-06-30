from typing import Protocol


class TextToSpeechError(Exception):
    """Raised when speech synthesis fails."""


class TextToSpeechProvider(Protocol):
    async def load_model(self) -> None:
        """Load the underlying TTS model."""

    async def synthesize_wav(self, text: str) -> bytes:
        """Synthesize text into WAV audio bytes."""
