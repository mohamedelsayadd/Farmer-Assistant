from typing import Protocol


class ASRError(Exception):
    """Raised when audio transcription fails."""


class ASRUnsupportedAudioError(ASRError):
    """Raised when the uploaded audio could not be decoded."""


class ASRProvider(Protocol):
    async def transcribe_wav(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes into text."""
