from agent.graph import FarmerAssistantAgent


def test_build_messages_injects_tool_context_as_system_message() -> None:
    messages = FarmerAssistantAgent._build_messages(
        history=[
            {"role": "user", "content": "درجة الحرارة كام؟"},
            {
                "role": "tool_context",
                "tool_name": "get_current_readings",
                "content": '{"devices": []}',
            },
            {"role": "assistant", "content": "درجة الحرارة ٢٢."},
        ],
        user_message="والرطوبة؟",
    )

    cached_context = messages[2]

    assert cached_context["role"] == "system"
    assert "Cached tool result from get_current_readings" in cached_context["content"]
    assert '{"devices": []}' in cached_context["content"]
    assert messages[-1] == {"role": "user", "content": "والرطوبة؟"}
