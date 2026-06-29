from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from models.schemas.chat import ChatRequest, ChatResponse
from services.wav_processor import transcribe_wav_file

router = APIRouter(prefix="/api/v1", tags=["chat"])

@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request) -> ChatResponse:
    request_body = await _parse_chat_request(request)
    return await request.app.state.chat_service.chat(request_body)


async def _parse_chat_request(request: Request) -> ChatRequest:
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
        return await _parse_form_chat_request(request)

    try:
        payload = await request.json()
    except JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Request body must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Request body must be a JSON object.")
    return _validate_chat_request(payload)


async def _parse_form_chat_request(request: Request) -> ChatRequest:
    form = await request.form()
    jwt = _get_form_str(form, "jwt")
    conversation_id = _get_form_str(form, "conversation_id")
    message = _get_form_str(form, "message")
    wav_file = form.get("wav_file")

    has_message = bool(message and message.strip())
    has_audio = isinstance(wav_file, UploadFile) and bool(wav_file.filename)
    if has_message == has_audio:
        raise HTTPException(status_code=422, detail="Send exactly one of message or wav_file.")

    if has_audio:
        message = await transcribe_wav_file(request, wav_file)

    return _validate_chat_request({"jwt": jwt, "conversation_id": conversation_id, "message": message or ""})


def _validate_chat_request(payload: dict[str, Any]) -> ChatRequest:
    try:
        return ChatRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _get_form_str(form: Any, field_name: str) -> str:
    value = form.get(field_name)
    if isinstance(value, UploadFile):
        raise HTTPException(status_code=422, detail=f"{field_name} must be a text field.")
    return str(value or "")
