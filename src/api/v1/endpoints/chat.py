from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from models.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request_body: ChatRequest, request: Request) -> ChatResponse:
    return await request.app.state.chat_service.chat(request_body)


@router.post("/chat/stream")
async def stream_chat(request_body: ChatRequest, request: Request) -> StreamingResponse:
    return StreamingResponse(
        request.app.state.chat_service.stream_chat(request_body),
        media_type="text/plain; charset=utf-8",
    )
