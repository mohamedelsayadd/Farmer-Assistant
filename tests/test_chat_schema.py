import pytest
from pydantic import ValidationError

from models.schemas.chat import ChatRequest, ChatResponse


def test_chat_request_rejects_empty_message() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(jwt="jwt", conversation_id="conversation-1", message="")


def test_chat_response_shape() -> None:
    response = ChatResponse(conversation_id="conversation-1", message="أهلا بيك")

    assert response.model_dump(exclude_none=True) == {
        "conversation_id": "conversation-1",
        "message": "أهلا بيك",
    }


def test_chat_response_accepts_optional_audio() -> None:
    response = ChatResponse(
        conversation_id="conversation-1",
        message="أهلا بيك",
        audio_wav_base64="UklGRg==",
        audio_content_type="audio/wav",
    )

    assert response.model_dump() == {
        "conversation_id": "conversation-1",
        "message": "أهلا بيك",
        "source": None,
        "disease": None,
        "audio_wav_base64": "UklGRg==",
        "audio_content_type": "audio/wav",
    }
