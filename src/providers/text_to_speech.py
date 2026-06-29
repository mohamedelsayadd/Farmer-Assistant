import asyncio
import io
import logging
from pathlib import Path
from time import perf_counter

from core.config import Settings

logger = logging.getLogger(__name__)


class TextToSpeechError(Exception):
    """Raised when speech synthesis fails."""


class TextToSpeechProvider:
    def __init__(self, settings: Settings) -> None:
        self._model_name = settings.tts_model
        self._device_map = settings.tts_device_map
        self._dtype = settings.tts_dtype
        self._sample_rate = settings.tts_sample_rate
        self._reference_audio_path = self._resolve_reference_audio_path(settings.tts_reference_audio_path)
        self._model = None
        self._lock = asyncio.Lock()

    async def synthesize_wav(self, text: str) -> bytes:
        async with self._lock:
            return await asyncio.to_thread(self._synthesize_wav_sync, text)

    def _synthesize_wav_sync(self, text: str) -> bytes:
        started_at = perf_counter()
        try:
            if not self._reference_audio_path.is_file():
                raise FileNotFoundError(f"TTS reference audio does not exist: {self._reference_audio_path}")

            audio = self._get_model().generate(
                text=text,
                ref_audio=str(self._reference_audio_path),
            )
            import soundfile as sf

            buffer = io.BytesIO()
            sf.write(buffer, audio[0], self._sample_rate, format="WAV")
            wav_bytes = buffer.getvalue()
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            logger.info(
                "text_to_speech_completed text_chars=%s audio_bytes=%s latency_ms=%s",
                len(text),
                len(wav_bytes),
                elapsed_ms,
            )
            return wav_bytes
        except Exception as exc:
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            logger.warning("text_to_speech_failed text_chars=%s latency_ms=%s", len(text), elapsed_ms, exc_info=True)
            raise TextToSpeechError("Speech synthesis failed") from exc

    def _get_model(self):
        if self._model is None:
            from omnivoice import OmniVoice
            import torch

            logger.info(
                "text_to_speech_model_loading model=%s device_map=%s dtype=%s",
                self._model_name,
                self._device_map,
                self._dtype,
            )
            self._model = OmniVoice.from_pretrained(
                self._model_name,
                device_map=self._device_map,
                dtype=self._get_torch_dtype(torch),
                load_asr=True,
            )
            logger.info("text_to_speech_model_loaded model=%s", self._model_name)
        return self._model

    def _get_torch_dtype(self, torch_module):
        try:
            return getattr(torch_module, self._dtype)
        except AttributeError as exc:
            raise TextToSpeechError(f"Unsupported TTS dtype: {self._dtype}") from exc

    @staticmethod
    def _resolve_reference_audio_path(path: str) -> Path:
        reference_path = Path(path).expanduser()
        if not reference_path.is_absolute():
            reference_path = Path.cwd() / reference_path
        return reference_path
