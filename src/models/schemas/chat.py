from pydantic import BaseModel, ConfigDict, Field


class UploadedImage(BaseModel):
    filename: str
    content_type: str | None = None
    content: bytes = Field(exclude=True)


class ChatRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    jwt: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    message: str = Field(min_length=1,max_length=7500)
    image: UploadedImage | None = Field(default=None, exclude=True)


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    source: str | None = None
    disease: str | None = None
    audio_wav_base64: str | None = None
    audio_content_type: str | None = None
