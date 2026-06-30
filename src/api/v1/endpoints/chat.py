from fastapi import APIRouter, Request

from models.schemas.chat import ChatResponse
from services.chat_request_processor import parse_chat_request
from services.voice_response_processor import add_voice_response

router = APIRouter(prefix="/api/v1", tags=["chat"])

@router.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
async def chat(request: Request) -> ChatResponse:
    request_body, should_generate_voice = await parse_chat_request(request)
    response = await request.app.state.chat_service.chat(request_body)
    if should_generate_voice:
        await add_voice_response(request, response)
    return response
