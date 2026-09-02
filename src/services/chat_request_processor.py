from json import JSONDecodeError
from typing import Any

from fastapi import HTTPException, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from models.schemas.chat import ChatRequest
from services.image_processor import read_image_file
from services.wav_processor import transcribe_wav_file

IMAGE_UPLOAD_MESSAGE = "تم رفع صورة نبات. شخص صورة النبات المرفوعة."


async def parse_chat_request(request: Request) -> tuple[ChatRequest, bool]:
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
        return await parse_form_chat_request(request)

    try:
        payload = await request.json()
    except JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Request body must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Request body must be a JSON object.")
    return validate_chat_request(payload), False


async def parse_form_chat_request(request: Request) -> tuple[ChatRequest, bool]:
    form = await request.form()
    jwt = get_form_str(form, "jwt")
    conversation_id = get_form_str(form, "conversation_id")
    message = get_form_str(form, "message")
    wav_file = form.get("wav_file")
    image_file = form.get("image_file")

    has_message = bool(message and message.strip())
    has_audio = isinstance(wav_file, UploadFile) and bool(wav_file.filename)
    has_image = isinstance(image_file, UploadFile) and bool(image_file.filename)
    if has_audio and (has_message or has_image):
        raise HTTPException(status_code=422, detail="wav_file cannot be sent with message or image_file.")
    if not has_audio and not has_message and not has_image:
        raise HTTPException(status_code=422, detail="Send message, wav_file, image_file, or message with image_file.")

    if has_audio:
        message = await transcribe_wav_file(request, wav_file)
    image = await read_image_file(request, image_file) if has_image else None
    if has_image and has_message:
        message = message.strip()
    elif has_image:
        message = IMAGE_UPLOAD_MESSAGE

    payload = {"jwt": jwt, "conversation_id": conversation_id, "message": message or "", "image": image}
    return validate_chat_request(payload), has_audio


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
