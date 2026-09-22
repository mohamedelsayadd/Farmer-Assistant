from fastapi import HTTPException, Request
from starlette.datastructures import UploadFile

from providers.ASR.interface import ASRError, ASRUnsupportedAudioError


async def transcribe_wav_file(request: Request, audio_file: UploadFile) -> str:
    # Any format ffmpeg can decode is accepted; the ASR backend decides decodability,
    # because browsers and phones send webm/m4a/amr blobs with no useful filename.
    audio_bytes = await audio_file.read()
    max_audio_bytes = request.app.state.asr_max_audio_bytes
    if len(audio_bytes) > max_audio_bytes:
        raise HTTPException(status_code=413, detail="audio_file is too large.")
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="audio_file must not be empty.")

    try:
        text = await request.app.state.asr.transcribe_wav(audio_bytes)
    except ASRUnsupportedAudioError as exc:
        raise HTTPException(status_code=422, detail="audio_file could not be decoded as audio.") from exc
    except ASRError as exc:
        raise HTTPException(status_code=503, detail="Audio transcription failed. Try again later.") from exc

    if not text.strip():
        raise HTTPException(status_code=422, detail="Audio transcription returned empty text.")
    return text
