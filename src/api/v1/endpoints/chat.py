from fastapi import APIRouter, Request

from models.schemas.chat import ChatResponse
from services.chat_request_processor import parse_chat_request

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
async def chat(request: Request) -> ChatResponse:
    request_body = await parse_chat_request(request)
    response = await request.app.state.chat_service.chat(request_body)
    if request_body.transcript is not None:
        response = response.model_copy(update={"transcript": request_body.transcript})
    return response
