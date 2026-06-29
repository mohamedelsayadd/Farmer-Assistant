from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints.chat import router
from models.schemas.chat import ChatRequest, ChatResponse
from providers.speech_to_text import SpeechToTextError


class FakeChatService:
    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        return ChatResponse(conversation_id=request.conversation_id, message=f"reply: {request.message}")


class FakeSpeechToText:
    def __init__(self, text: str = "درجة الحرارة كام؟", should_fail: bool = False) -> None:
        self._text = text
        self._should_fail = should_fail

    async def transcribe_wav(self, audio_bytes: bytes) -> str:
        assert audio_bytes == b"fake-wav"
        if self._should_fail:
            raise SpeechToTextError("failed")
        return self._text


def make_client(speech_to_text: FakeSpeechToText | None = None) -> tuple[TestClient, FakeChatService]:
    app = FastAPI()
    app.include_router(router)
    chat_service = FakeChatService()
    app.state.chat_service = chat_service
    app.state.speech_to_text = speech_to_text or FakeSpeechToText()
    app.state.stt_max_audio_bytes = 1024
    return TestClient(app), chat_service


def test_chat_endpoint_keeps_json_request_shape() -> None:
    client, chat_service = make_client()

    response = client.post(
        "/api/v1/chat",
        json={
            "jwt": "runtime-jwt",
            "conversation_id": "conversation-1",
            "message": "درجة الحرارة كام؟",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "conversation_id": "conversation-1",
        "message": "reply: درجة الحرارة كام؟",
    }
    assert chat_service.requests == [
        ChatRequest(jwt="runtime-jwt", conversation_id="conversation-1", message="درجة الحرارة كام؟")
    ]


def test_chat_endpoint_accepts_multipart_wav_file() -> None:
    client, chat_service = make_client()

    response = client.post(
        "/api/v1/chat",
        data={"jwt": "runtime-jwt", "conversation_id": "conversation-1"},
        files={"wav_file": ("voice.wav", b"fake-wav", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "conversation_id": "conversation-1",
        "message": "reply: درجة الحرارة كام؟",
    }
    assert chat_service.requests == [
        ChatRequest(jwt="runtime-jwt", conversation_id="conversation-1", message="درجة الحرارة كام؟")
    ]


def test_chat_endpoint_accepts_form_text_message() -> None:
    client, chat_service = make_client()

    response = client.post(
        "/api/v1/chat",
        data={
            "jwt": "runtime-jwt",
            "conversation_id": "conversation-1",
            "message": "درجة الحرارة كام؟",
        },
    )

    assert response.status_code == 200
    assert chat_service.requests == [
        ChatRequest(jwt="runtime-jwt", conversation_id="conversation-1", message="درجة الحرارة كام؟")
    ]


def test_chat_endpoint_rejects_multipart_with_message_and_wav_file() -> None:
    client, _ = make_client()

    response = client.post(
        "/api/v1/chat",
        data={
            "jwt": "runtime-jwt",
            "conversation_id": "conversation-1",
            "message": "درجة الحرارة كام؟",
        },
        files={"wav_file": ("voice.wav", b"fake-wav", "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Send exactly one of message or wav_file."


def test_chat_endpoint_rejects_multipart_without_message_or_wav_file() -> None:
    client, _ = make_client()

    response = client.post(
        "/api/v1/chat",
        data={"jwt": "runtime-jwt", "conversation_id": "conversation-1"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Send exactly one of message or wav_file."


def test_chat_endpoint_rejects_non_wav_audio() -> None:
    client, _ = make_client()

    response = client.post(
        "/api/v1/chat",
        data={"jwt": "runtime-jwt", "conversation_id": "conversation-1"},
        files={"wav_file": ("voice.mp3", b"fake-wav", "audio/mpeg")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "wav_file must be a WAV audio file."


def test_chat_endpoint_rejects_empty_transcription() -> None:
    client, _ = make_client(speech_to_text=FakeSpeechToText(text=""))

    response = client.post(
        "/api/v1/chat",
        data={"jwt": "runtime-jwt", "conversation_id": "conversation-1"},
        files={"wav_file": ("voice.wav", b"fake-wav", "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Audio transcription returned empty text."


def test_chat_endpoint_returns_503_when_transcription_fails() -> None:
    client, _ = make_client(speech_to_text=FakeSpeechToText(should_fail=True))

    response = client.post(
        "/api/v1/chat",
        data={"jwt": "runtime-jwt", "conversation_id": "conversation-1"},
        files={"wav_file": ("voice.wav", b"fake-wav", "audio/wav")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Audio transcription failed. Try again later."
