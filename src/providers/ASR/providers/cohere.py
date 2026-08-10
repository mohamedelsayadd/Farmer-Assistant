import asyncio
import logging
import os
import tempfile
from time import perf_counter

from core.config import Settings
from core.logging import json_preview
from providers.ASR.interface import ASRError

logger = logging.getLogger(__name__)

# The Cohere ASR feature extractor is trained on 16 kHz mono audio and chunks
# anything longer than its own `max_audio_clip_s` internally.
SAMPLING_RATE = 16000

# Values accepted by ASR_DTYPE, mapped to the matching `torch` attribute name.
SUPPORTED_DTYPES = {
    "float16": "float16",
    "fp16": "float16",
    "half": "float16",
    "bfloat16": "bfloat16",
    "bf16": "bfloat16",
    "float32": "float32",
    "fp32": "float32",
    "float": "float32",
}


def resolve_torch_dtype(dtype_name: str):
    """Map an ASR_DTYPE value onto a torch dtype, importing torch lazily."""
    key = dtype_name.lower().strip()
    if key not in SUPPORTED_DTYPES:
        supported = ", ".join(sorted(set(SUPPORTED_DTYPES)))
        raise ValueError(f"Unsupported ASR_DTYPE: {dtype_name}. Supported values: {supported}")

    import torch

    return getattr(torch, SUPPORTED_DTYPES[key])


class CohereASRProvider:
    def __init__(self, settings: Settings) -> None:
        # The Cohere processor builds its decoder prompt from the language code,
        # so unlike faster-whisper it has no auto-detection mode.
        language = (settings.asr_language or "").strip()
        if not language:
            raise ValueError("ASR_LANGUAGE is required for the cohere provider; it has no auto detection.")
        # Fail at startup rather than on the first request if the dtype is wrong.
        resolve_torch_dtype(settings.asr_dtype)

        self._model_name = settings.asr_model
        self._device = settings.asr_device
        self._dtype = settings.asr_dtype
        self._language = language
        self._max_new_tokens = settings.asr_max_new_tokens
        self._processor = None
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
            import torch
            from transformers.audio_utils import load_audio

            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as audio_file:
                audio_file.write(audio_bytes)
                path = audio_file.name

            # `load_audio` takes a path, resamples to 16 kHz, and downmixes to mono.
            audio = load_audio(path, sampling_rate=SAMPLING_RATE)
            processor, model = self._get_model()
            inputs = processor(
                audio,
                language=self._language,
                sampling_rate=SAMPLING_RATE,
                return_tensors="pt",
            )
            inputs = inputs.to(model.device, dtype=model.dtype)
            with torch.inference_mode():
                outputs = model.generate(**inputs, max_new_tokens=self._max_new_tokens)
            text = processor.batch_decode(outputs, skip_special_tokens=True)[0].strip()

            elapsed_ms = int((perf_counter() - started_at) * 1000)
            logger.info(
                "asr_completed provider=cohere audio_bytes=%s text_chars=%s latency_ms=%s text=%s",
                len(audio_bytes),
                len(text),
                elapsed_ms,
                json_preview(text),
            )
            return text
        except Exception as exc:
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            logger.exception(
                "asr_failed provider=cohere audio_bytes=%s latency_ms=%s",
                len(audio_bytes),
                elapsed_ms,
            )
            raise ASRError("Audio transcription failed") from exc
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    logger.warning("asr_temp_file_cleanup_failed provider=cohere")

    def _get_model(self):
        if self._model is None:
            from transformers import AutoProcessor, CohereAsrForConditionalGeneration

            logger.info(
                "asr_model_loading provider=cohere model=%s device=%s dtype=%s",
                self._model_name,
                self._device,
                self._dtype,
            )
            self._processor = AutoProcessor.from_pretrained(self._model_name)
            model = CohereAsrForConditionalGeneration.from_pretrained(
                self._model_name,
                dtype=resolve_torch_dtype(self._dtype),
                device_map=self._device,
            )
            model.eval()
            self._model = model
            logger.info("asr_model_loaded provider=cohere model=%s", self._model_name)
        return self._processor, self._model
