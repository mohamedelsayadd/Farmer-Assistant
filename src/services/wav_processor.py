from fastapi import HTTPException, Request
from starlette.datastructures import UploadFile

from providers.ASR.interface import ASRError


def is_wav_file(file: UploadFile) -> bool:
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    return filename.endswith(".wav") or content_type in {"audio/wav", "audio/wave", "audio/x-wav"}


async def transcribe_wav_file(request: Request, wav_file: UploadFile) -> str:
    if not is_wav_file(wav_file):
        raise HTTPException(status_code=422, detail="wav_file must be a WAV audio file.")

    audio_bytes = await wav_file.read()
    max_audio_bytes = request.app.state.asr_max_audio_bytes
    if len(audio_bytes) > max_audio_bytes:
        raise HTTPException(status_code=413, detail="wav_file is too large.")
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="wav_file must not be empty.")

    try:
        text = await request.app.state.asr.transcribe_wav(audio_bytes)
    except ASRError as exc:
        raise HTTPException(status_code=503, detail="Audio transcription failed. Try again later.") from exc

    if not text.strip():
        raise HTTPException(status_code=422, detail="Audio transcription returned empty text.")
    return text
