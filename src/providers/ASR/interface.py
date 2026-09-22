from typing import Protocol


class ASRError(Exception):
    """Raised when audio transcription fails."""


class ASRUnsupportedAudioError(ASRError):
    """Raised when the uploaded audio could not be decoded."""


class ASRProvider(Protocol):
    async def load_model(self) -> None:
        """Prepare the provider. Local providers load weights; remote providers do nothing."""

    async def transcribe_wav(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes into text."""
