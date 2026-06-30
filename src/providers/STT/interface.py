from typing import Protocol


class SpeechToTextError(Exception):
    """Raised when audio transcription fails."""


class SpeechToTextProvider(Protocol):
    async def load_model(self) -> None:
        """Load the underlying STT model."""

    async def transcribe_wav(self, audio_bytes: bytes) -> str:
        """Transcribe WAV audio bytes into text."""
