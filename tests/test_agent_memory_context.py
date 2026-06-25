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
    assert "Any message related to agriculture, farm devices, or device readings is in scope" in system_prompt
    assert "Refuse any question outside agriculture, devices, or farm/device readings" in system_prompt
    assert "آسف، مقدرش أرد على سؤالك." in system_prompt


def test_system_prompt_sets_response_language_and_blocks_pre_2026_readings() -> None:
    messages = FarmerAssistantAgent._build_messages(history=[], user_message="Show readings from 2025")
    system_prompt = messages[0]["content"]

    assert "Reply in English only when the user's message is fully English" in system_prompt
    assert "Arabic or mixed Arabic/English" in system_prompt
    assert "Understand user messages in Arabic or English" in system_prompt
    assert "What are the latest readings?" in system_prompt
    assert "Give me a summary for last week" in system_prompt
    assert "Never answer or call tools for readings before 2026-01-01" in system_prompt
    assert "القراءات قبل 2026 غير متاحة." in system_prompt
