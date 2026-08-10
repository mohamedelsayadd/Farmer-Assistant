import asyncio
import logging
import os
import tempfile
from time import perf_counter

from core.config import Settings
from core.logging import json_preview
from providers.ASR.interface import ASRError

logger = logging.getLogger(__name__)


class FasterWhisperASRProvider:
    def __init__(self, settings: Settings) -> None:
        self._model_name = settings.asr_model
        self._device = settings.asr_device
        self._compute_type = settings.asr_compute_type
        self._language = settings.asr_language or None
        self._model = None
        self._lock = asyncio.Lock()

    async def load_model(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._get_model)

    async def transcribe_wav(self, audio_bytes: bytes) -> str:
        async with self._lock:
            return await asyncio.to_thread(self._transcribe_wav_sync, audio_bytes)

    def _transcribe_wav_sync(self, audio_bytes: bytes) -> str:
        started_at = perf_counter()
        path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as audio_file:
                audio_file.write(audio_bytes)
                path = audio_file.name

            segments, _ = self._get_model().transcribe(path, language=self._language)
            text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            logger.info(
                "asr_completed provider=faster_whisper audio_bytes=%s text_chars=%s latency_ms=%s text=%s",
                len(audio_bytes),
                len(text),
                elapsed_ms,
                json_preview(text),
            )
            return text
        except Exception as exc:
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            logger.exception(
                "asr_failed provider=faster_whisper audio_bytes=%s latency_ms=%s",
                len(audio_bytes),
                elapsed_ms,
            )
            raise ASRError("Audio transcription failed") from exc
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    logger.warning("asr_temp_file_cleanup_failed provider=faster_whisper")

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            logger.info(
                "asr_model_loading provider=faster_whisper model=%s device=%s compute_type=%s",
                self._model_name,
                self._device,
                self._compute_type,
            )
            self._model = WhisperModel(self._model_name, device=self._device, compute_type=self._compute_type)
            logger.info("asr_model_loaded provider=faster_whisper model=%s", self._model_name)
        return self._model
