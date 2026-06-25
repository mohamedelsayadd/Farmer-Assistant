from agent.graph import FarmerAssistantAgent


def test_build_messages_does_not_merge_tool_context_into_system_message() -> None:
    messages = FarmerAssistantAgent._build_messages(
        history=[
            {"role": "user", "content": "درجة الحرارة كام؟"},
            {"role": "assistant", "content": "درجة الحرارة ٢٢."},
        ],
        user_message="والرطوبة؟",
    )

    system_messages = [message for message in messages if message["role"] == "system"]

    assert system_messages == [messages[0]]
    assert "Cached tool result" not in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "درجة الحرارة كام؟"}
    assert messages[2] == {"role": "assistant", "content": "درجة الحرارة ٢٢."}
    assert messages[-1] == {"role": "user", "content": "والرطوبة؟"}


def test_build_messages_injects_current_date() -> None:
    messages = FarmerAssistantAgent._build_messages(history=[], user_message="آخر أسبوع؟")

    assert "تاريخ النهاردة:" in messages[0]["content"]


def test_system_prompt_restricts_answers_to_agriculture_and_device_readings() -> None:
    messages = FarmerAssistantAgent._build_messages(history=[], user_message="اكتبلي كود بايثون")
    system_prompt = messages[0]["content"]

    assert "Only answer questions about agriculture" in system_prompt
    assert "Refuse any question outside agriculture or farm/device readings" in system_prompt
    assert "أقدر أساعدك بس في أسئلة الزراعة وقراءات أجهزة المزرعة" in system_prompt
