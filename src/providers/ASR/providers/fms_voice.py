import logging
from time import perf_counter

import httpx

from core.config import Settings
from core.logging import json_preview
from providers.ASR.interface import ASRError, ASRUnsupportedAudioError

logger = logging.getLogger(__name__)

# The FMS-Voice processor builds its decoder prompt from the language code, so it
# accepts these two values only (see ASR-API-Contract.md).
SUPPORTED_LANGUAGES = {"ar", "en"}

# The service returns 415 when ffmpeg cannot decode the upload. That is the only
# status the caller can act on, so it is the only one mapped to its own error.
UNSUPPORTED_AUDIO_STATUS = 415

# The protocol hands us bytes only, so the original filename is unavailable. The
# service probes the content with ffmpeg, so a fixed placeholder name is enough.
UPLOAD_FILENAME = "audio"


class FMSVoiceASRProvider:
    """Transcribes audio through the remote FMS-Voice service instead of loading a model."""

    def __init__(self, settings: Settings) -> None:
        language = (settings.asr_language or "").strip().lower()
        # An empty value means "let the service apply its own default".
        if language and language not in SUPPORTED_LANGUAGES:
            supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
            raise ValueError(
                f"Unsupported ASR_LANGUAGE for the fms_voice provider: {settings.asr_language}. "
                f"Supported values: {supported}"
            )

        self._base_url = settings.asr_remote_base_url
        self._transcribe_path = settings.asr_remote_transcribe_path
        self._timeout = settings.asr_remote_timeout_seconds
        self._language = language or None

    async def load_model(self) -> None:
        """No-op: the weights live in the FMS-Voice service, not in this process."""
        logger.info("asr_model_skipped provider=fms_voice base_url=%s", self._base_url)

    async def transcribe_wav(self, audio_bytes: bytes) -> str:
        started_at = perf_counter()
        logger.info(
            "asr_remote_started provider=fms_voice path=%s audio_bytes=%s language=%s",
            self._transcribe_path,
            len(audio_bytes),
            self._language,
        )

        files = {"file": (UPLOAD_FILENAME, audio_bytes, "application/octet-stream")}
        data = {"language": self._language} if self._language else {}
        try:
            async with self._build_client() as client:
                response = await client.post(self._transcribe_path, files=files, data=data)
        except httpx.HTTPError as exc:
            self._log_failure(None, audio_bytes, started_at, str(exc))
            raise ASRError("Audio transcription failed") from exc

        if response.status_code != httpx.codes.OK:
            self._log_failure(response.status_code, audio_bytes, started_at, detail(response))
            if response.status_code == UNSUPPORTED_AUDIO_STATUS:
                raise ASRUnsupportedAudioError("Audio could not be decoded")
            raise ASRError("Audio transcription failed")

        try:
            payload = response.json()
            text = payload["text"]
        except (ValueError, KeyError, TypeError) as exc:
            self._log_failure(response.status_code, audio_bytes, started_at, "malformed response body")
            raise ASRError("Audio transcription failed") from exc
        if not isinstance(text, str):
            self._log_failure(response.status_code, audio_bytes, started_at, "text field is not a string")
            raise ASRError("Audio transcription failed")

        text = text.strip()
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        logger.info(
            "asr_completed provider=fms_voice audio_bytes=%s text_chars=%s latency_ms=%s rtfx=%s text=%s",
            len(audio_bytes),
            len(text),
            elapsed_ms,
            payload.get("rtfx") if isinstance(payload, dict) else None,
            json_preview(text),
        )
        return text

    def _build_client(self) -> httpx.AsyncClient:
        # A short connect timeout turns an unreachable service into a fast 503
        # instead of a hang; the read timeout covers the service's request queue.
        timeout = httpx.Timeout(self._timeout, connect=5.0)
        return httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    def _log_failure(self, status_code: int | None, audio_bytes: bytes, started_at: float, detail: str) -> None:
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        logger.error(
            "asr_failed provider=fms_voice status_code=%s audio_bytes=%s latency_ms=%s detail=%s",
            status_code,
            len(audio_bytes),
            elapsed_ms,
            detail,
        )


def detail(response: httpx.Response) -> str:
    """Pull the service's `{"detail": ...}` error message out for the failure log."""
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(payload, dict) and "detail" in payload:
        return str(payload["detail"])[:200]
    return response.text[:200]
