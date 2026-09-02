from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints.chat import router
from models.schemas.chat import ChatRequest, ChatResponse
from providers.ASR.interface import ASRError
from providers.TTS.interface import TextToSpeechError


class FakeChatService:
    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        if request.image is not None:
            return ChatResponse(
                conversation_id=request.conversation_id,
                message="reply: plant diagnosis",
                source="yolo",
                disease="potato early blight",
            )
        return ChatResponse(conversation_id=request.conversation_id, message=f"reply: {request.message}")


class FakeASR:
    def __init__(self, text: str = "درجة الحرارة كام؟", should_fail: bool = False) -> None:
        self._text = text
        self._should_fail = should_fail

    async def transcribe_wav(self, audio_bytes: bytes) -> str:
        assert audio_bytes == b"fake-wav"
        if self._should_fail:
            raise ASRError("failed")
        return self._text


class FakeTextToSpeech:
    def __init__(self, wav_bytes: bytes = b"fake-tts-wav", should_fail: bool = False) -> None:
        self.requests: list[str] = []
        self._wav_bytes = wav_bytes
        self._should_fail = should_fail

    async def synthesize_wav(self, text: str) -> bytes:
        self.requests.append(text)
        if self._should_fail:
            raise TextToSpeechError("failed")
        return self._wav_bytes


def make_client(
    asr: FakeASR | None = None,
    text_to_speech: FakeTextToSpeech | None = None,
) -> tuple[TestClient, FakeChatService, FakeTextToSpeech]:
    app = FastAPI()
    app.include_router(router)
    chat_service = FakeChatService()
    tts = text_to_speech or FakeTextToSpeech()
    app.state.chat_service = chat_service
    app.state.asr = asr or FakeASR()
    app.state.text_to_speech = tts
    app.state.asr_max_audio_bytes = 1024
    app.state.plant_disease_max_image_bytes = 1024
    return TestClient(app), chat_service, tts


def test_chat_endpoint_keeps_json_request_shape() -> None:
    client, chat_service, tts = make_client()

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
    assert tts.requests == []


def test_chat_endpoint_accepts_multipart_wav_file() -> None:
    client, chat_service, tts = make_client()

    response = client.post(
        "/api/v1/chat",
        data={"jwt": "runtime-jwt", "conversation_id": "conversation-1"},
        files={"wav_file": ("voice.wav", b"fake-wav", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "conversation_id": "conversation-1",
        "message": "reply: درجة الحرارة كام؟",
        "audio_wav_base64": "ZmFrZS10dHMtd2F2",
        "audio_content_type": "audio/wav",
    }
    assert chat_service.requests == [
        ChatRequest(jwt="runtime-jwt", conversation_id="conversation-1", message="درجة الحرارة كام؟")
    ]
    assert tts.requests == ["reply: درجة الحرارة كام؟"]


def test_chat_endpoint_returns_text_only_when_tts_fails() -> None:
    client, chat_service, tts = make_client(text_to_speech=FakeTextToSpeech(should_fail=True))

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
    assert tts.requests == ["reply: درجة الحرارة كام؟"]


def test_chat_endpoint_accepts_form_text_message() -> None:
    client, chat_service, _ = make_client()

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


def test_chat_endpoint_accepts_multipart_image_file() -> None:
    client, chat_service, _ = make_client()

    response = client.post(
        "/api/v1/chat",
        data={"jwt": "runtime-jwt", "conversation_id": "conversation-1"},
        files={"image_file": ("plant.jpg", b"fake-image", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "conversation_id": "conversation-1",
        "message": "reply: plant diagnosis",
        "source": "yolo",
        "disease": "potato early blight",
    }
    assert len(chat_service.requests) == 1
    request = chat_service.requests[0]
    assert request.message == "تم رفع صورة نبات. شخص صورة النبات المرفوعة."
    assert request.image is not None
    assert request.image.filename == "plant.jpg"
    assert request.image.content == b"fake-image"


def test_chat_endpoint_rejects_multipart_with_message_and_wav_file() -> None:
    client, _, _ = make_client()

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
    assert response.json()["detail"] == "wav_file cannot be sent with message or image_file."


def test_chat_endpoint_rejects_multipart_without_message_or_wav_file() -> None:
    client, _, _ = make_client()

    response = client.post(
        "/api/v1/chat",
        data={"jwt": "runtime-jwt", "conversation_id": "conversation-1"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Send message, wav_file, image_file, or message with image_file."


def test_chat_endpoint_accepts_multipart_with_message_and_image_file() -> None:
    client, chat_service, _ = make_client()

    response = client.post(
        "/api/v1/chat",
        data={
            "jwt": "runtime-jwt",
            "conversation_id": "conversation-1",
            "message": "درجة الحرارة كام؟",
        },
        files={"image_file": ("plant.jpg", b"fake-image", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "conversation_id": "conversation-1",
        "message": "reply: plant diagnosis",
        "source": "yolo",
        "disease": "potato early blight",
    }
    assert len(chat_service.requests) == 1
    request = chat_service.requests[0]
    assert request.message == "درجة الحرارة كام؟"
    assert request.image is not None
    assert request.image.filename == "plant.jpg"


def test_chat_endpoint_rejects_multipart_with_wav_and_image_file() -> None:
    client, _, _ = make_client()

    response = client.post(
        "/api/v1/chat",
        data={"jwt": "runtime-jwt", "conversation_id": "conversation-1"},
        files={
            "wav_file": ("voice.wav", b"fake-wav", "audio/wav"),
            "image_file": ("plant.jpg", b"fake-image", "image/jpeg"),
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "wav_file cannot be sent with message or image_file."


def test_chat_endpoint_rejects_unsupported_image_type() -> None:
    client, _, _ = make_client()

    response = client.post(
        "/api/v1/chat",
        data={"jwt": "runtime-jwt", "conversation_id": "conversation-1"},
        files={"image_file": ("plant.gif", b"fake-image", "image/gif")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "image_file must be one of: ['.jpeg', '.jpg', '.png', '.webp']."


def test_chat_endpoint_rejects_empty_image() -> None:
    client, _, _ = make_client()

    response = client.post(
        "/api/v1/chat",
        data={"jwt": "runtime-jwt", "conversation_id": "conversation-1"},
        files={"image_file": ("plant.jpg", b"", "image/jpeg")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "image_file must not be empty."


def test_chat_endpoint_rejects_large_image() -> None:
    client, _, _ = make_client()

    response = client.post(
        "/api/v1/chat",
        data={"jwt": "runtime-jwt", "conversation_id": "conversation-1"},
        files={"image_file": ("plant.jpg", b"x" * 1025, "image/jpeg")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "image_file is too large."


def test_chat_endpoint_rejects_non_wav_audio() -> None:
    client, _, _ = make_client()

    response = client.post(
        "/api/v1/chat",
        data={"jwt": "runtime-jwt", "conversation_id": "conversation-1"},
        files={"wav_file": ("voice.mp3", b"fake-wav", "audio/mpeg")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "wav_file must be a WAV audio file."


def test_chat_endpoint_rejects_empty_transcription() -> None:
    client, _, _ = make_client(asr=FakeASR(text=""))

    response = client.post(
        "/api/v1/chat",
        data={"jwt": "runtime-jwt", "conversation_id": "conversation-1"},
        files={"wav_file": ("voice.wav", b"fake-wav", "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Audio transcription returned empty text."


def test_chat_endpoint_returns_503_when_transcription_fails() -> None:
    client, _, _ = make_client(asr=FakeASR(should_fail=True))

    response = client.post(
        "/api/v1/chat",
        data={"jwt": "runtime-jwt", "conversation_id": "conversation-1"},
        files={"wav_file": ("voice.wav", b"fake-wav", "audio/wav")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Audio transcription failed. Try again later."
