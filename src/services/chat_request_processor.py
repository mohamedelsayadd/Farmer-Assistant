from json import JSONDecodeError
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from models.schemas.chat import ChatRequest, UploadedImage
from providers.ASR.interface import ASRError, ASRUnsupportedAudioError

IMAGE_UPLOAD_MESSAGE = "[The user uploaded a plant image with no text. Diagnose the uploaded plant image.]"
ALLOWED_IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".png", ".webp"}


async def parse_chat_request(request: Request) -> ChatRequest:
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
        return await parse_form_chat_request(request)

    try:
        payload = await request.json()
    except JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Request body must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Request body must be a JSON object.")
    return validate_chat_request(payload)


async def parse_form_chat_request(request: Request) -> ChatRequest:
    form = await request.form()
    jwt = get_form_str(form, "jwt")
    conversation_id = get_form_str(form, "conversation_id")
    message = get_form_str(form, "message")
    # wav_file is the deprecated alias of audio_file, kept so existing clients keep working.
    audio_file = form.get("audio_file") or form.get("wav_file")
    image_file = form.get("image_file")

    has_message = bool(message and message.strip())
    has_audio = isinstance(audio_file, UploadFile) and bool(audio_file.filename)
    has_image = isinstance(image_file, UploadFile) and bool(image_file.filename)
    if has_audio and (has_message or has_image):
        raise HTTPException(status_code=422, detail="audio_file cannot be sent with message or image_file.")
    if not has_audio and not has_message and not has_image:
        raise HTTPException(status_code=422, detail="Send message, audio_file, image_file, or message with image_file.")

    transcript = None
    if has_audio:
        message = transcript = await read_audio_file(request, audio_file)
    image = await read_image_file(request, image_file) if has_image else None
    if has_image and has_message:
        message = message.strip()
    elif has_image:
        message = IMAGE_UPLOAD_MESSAGE

    payload = {"jwt": jwt, "conversation_id": conversation_id, "message": message or "", "image": image}
    if transcript is not None:
        payload["transcript"] = transcript
    return validate_chat_request(payload)


def validate_chat_request(payload: dict[str, Any]) -> ChatRequest:
    try:
        return ChatRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def get_form_str(form: Any, field_name: str) -> str:
    value = form.get(field_name)
    if isinstance(value, UploadFile):
        raise HTTPException(status_code=422, detail=f"{field_name} must be a text field.")
    return str(value or "")


async def read_audio_file(request: Request, audio_file: UploadFile) -> str:
    # Any format ffmpeg can decode is accepted; the ASR backend decides decodability,
    # because browsers and phones send webm/m4a/amr blobs with no useful filename.
    audio_bytes = await audio_file.read()
    if len(audio_bytes) > request.app.state.asr_max_audio_bytes:
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


async def read_image_file(request: Request, image_file: UploadFile) -> UploadedImage:
    if Path(image_file.filename or "").suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"image_file must be one of: {sorted(ALLOWED_IMAGE_EXTENSIONS)}.")

    image_bytes = await image_file.read()
    if len(image_bytes) > request.app.state.plant_disease_max_image_bytes:
        raise HTTPException(status_code=413, detail="image_file is too large.")
    if not image_bytes:
        raise HTTPException(status_code=422, detail="image_file must not be empty.")

    return UploadedImage(
        filename=image_file.filename or "plant-image",
        content_type=image_file.content_type,
        content=image_bytes,
    )
