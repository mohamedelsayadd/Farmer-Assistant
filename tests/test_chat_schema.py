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


def test_chat_response_has_no_audio_fields() -> None:
    assert set(ChatResponse.model_fields) == {"conversation_id", "message", "source", "disease", "transcript"}
