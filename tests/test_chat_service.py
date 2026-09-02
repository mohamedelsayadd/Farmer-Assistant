import pytest

from agent.graph import AgentResult, ToolContext
from models.schemas.chat import ChatRequest
from services.chat_service import ChatService


class FakeMemory:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, str]] = []

    async def load(self, conversation_id: str) -> list[dict]:
        assert conversation_id == "conversation-1"
        return []

    async def append(self, conversation_id: str, role: str, content: str) -> None:
        self.events.append((role, conversation_id, content))

class FakeAgent:
    async def run(self, conversation_id: str, jwt: str, user_message: str, history: list[dict], image: object | None = None) -> AgentResult:
        assert conversation_id == "conversation-1"
        assert jwt == "runtime-jwt"
        assert user_message == "درجة الحرارة كام؟"
        assert history == []
        assert image is None
        return AgentResult(
            response="درجة الحرارة ٢٢.",
            tool_contexts=[ToolContext(tool_name="get_current_readings", content='{"devices": []}')],
        )


class FakePlantAgent:
    async def run(self, conversation_id: str, jwt: str, user_message: str, history: list[dict], image: object | None = None) -> AgentResult:
        assert image is not None
        return AgentResult(
            response="تم تشخيص المرض.",
            tool_contexts=[
                ToolContext(
                    tool_name="plant_diseases_detection",
                    content='{"source": "yolo", "disease": "potato early blight"}',
                )
            ],
        )


@pytest.mark.asyncio
async def test_chat_service_saves_only_user_and_assistant_messages() -> None:
    memory = FakeMemory()
    service = ChatService(memory=memory, agent=FakeAgent())  # type: ignore[arg-type]

    response = await service.chat(
        ChatRequest(
            jwt="runtime-jwt",
            conversation_id="conversation-1",
            message="درجة الحرارة كام؟",
        )
    )

    assert response.message == "درجة الحرارة ٢٢."
    assert memory.events == [
        ("user", "conversation-1", "درجة الحرارة كام؟"),
        ("assistant", "conversation-1", "درجة الحرارة ٢٢."),
    ]


@pytest.mark.asyncio
async def test_chat_service_returns_plant_disease_source_without_saving_image_bytes() -> None:
    from models.schemas.chat import UploadedImage

    memory = FakeMemory()
    service = ChatService(memory=memory, agent=FakePlantAgent())  # type: ignore[arg-type]

    response = await service.chat(
        ChatRequest(
            jwt="runtime-jwt",
            conversation_id="conversation-1",
            message="تم رفع صورة نبات. شخص صورة النبات المرفوعة.",
            image=UploadedImage(filename="plant.jpg", content_type="image/jpeg", content=b"fake-image"),
        )
    )

    assert response.message == "تم تشخيص المرض."
    assert response.source == "yolo"
    assert response.disease == "potato early blight"
    assert memory.events == [
        ("user", "conversation-1", "تم رفع صورة نبات. شخص صورة النبات المرفوعة."),
        ("assistant", "conversation-1", "تم تشخيص المرض."),
    ]
