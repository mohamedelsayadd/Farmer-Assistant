from json import JSONDecodeError
from typing import Any

from fastapi import HTTPException, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from models.schemas.chat import ChatRequest
from services.wav_processor import transcribe_wav_file


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

    has_message = bool(message and message.strip())
    has_audio = isinstance(wav_file, UploadFile) and bool(wav_file.filename)
    if has_message == has_audio:
        raise HTTPException(status_code=422, detail="Send exactly one of message or wav_file.")

    if has_audio:
        message = await transcribe_wav_file(request, wav_file)

    return validate_chat_request({"jwt": jwt, "conversation_id": conversation_id, "message": message or ""}), False #has_audio


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
