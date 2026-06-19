from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    jwt: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
