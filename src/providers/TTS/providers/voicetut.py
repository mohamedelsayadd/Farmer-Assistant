import asyncio
import logging
import os
import tempfile
from time import perf_counter

from core.config import Settings
from providers.TTS.interface import TextToSpeechError

logger = logging.getLogger(__name__)


class VoiceTutTextToSpeechProvider:
    def __init__(self, settings: Settings) -> None:
        self._model_name = settings.tts_model
        self._device = settings.tts_device
        self._dtype = settings.tts_dtype
        self._speaker = settings.tts_speaker
        self._num_step = settings.tts_num_step
        self._guidance_scale = settings.tts_guidance_scale
        self._speed = settings.tts_speed
        self._model = None
        self._lock = asyncio.Lock()

    async def load_model(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._get_model)

    async def synthesize_wav(self, text: str) -> bytes:
        async with self._lock:
            return await asyncio.to_thread(self._synthesize_wav_sync, text)

    def _synthesize_wav_sync(self, text: str) -> bytes:
        started_at = perf_counter()
        path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as audio_file:
                path = audio_file.name

            self._get_model().synthesize(
                text,
                speaker=self._speaker,
                num_step=self._num_step,
                guidance_scale=self._guidance_scale,
                speed=self._speed,
                output=path,
            )
            with open(path, "rb") as audio_file:
                wav_bytes = audio_file.read()

            elapsed_ms = int((perf_counter() - started_at) * 1000)
            logger.info(
                "text_to_speech_completed provider=voicetut text_chars=%s audio_bytes=%s latency_ms=%s",
                len(text),
                len(wav_bytes),
                elapsed_ms,
            )
            return wav_bytes
        except Exception as exc:
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            logger.warning(
                "text_to_speech_failed provider=voicetut text_chars=%s latency_ms=%s",
                len(text),
                elapsed_ms,
                exc_info=True,
            )
            raise TextToSpeechError("Speech synthesis failed") from exc
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    logger.warning("text_to_speech_temp_file_cleanup_failed provider=voicetut")

    def _get_model(self):
        if self._model is None:
            from voicetut_tts import VoiceTutTTS

            logger.info(
                "text_to_speech_model_loading provider=voicetut model=%s device=%s dtype=%s speaker=%s num_step=%s guidance_scale=%s speed=%s",
                self._model_name,
                self._device,
                self._dtype,
                self._speaker,
                self._num_step,
                self._guidance_scale,
                self._speed,
            )
            self._model = VoiceTutTTS.from_pretrained(
                self._model_name,
                device=self._device,
                dtype=self._dtype,
            )
            logger.info("text_to_speech_model_loaded provider=voicetut model=%s", self._model_name)
        return self._model
