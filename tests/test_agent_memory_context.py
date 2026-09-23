from agent.agent import build_messages, system_prompt


def test_build_messages_keeps_history_as_plain_turns_without_system_or_tool_context() -> None:
    messages = build_messages(
        history=[
            {"role": "user", "content": "درجة الحرارة كام؟"},
            {"role": "assistant", "content": "درجة الحرارة ٢٢."},
        ],
        user_message="والرطوبة؟",
    )

    assert messages == [
        {"role": "user", "content": "درجة الحرارة كام؟"},
        {"role": "assistant", "content": "درجة الحرارة ٢٢."},
        {"role": "user", "content": "والرطوبة؟"},
    ]


def test_system_prompt_injects_current_date() -> None:
    assert "تاريخ النهاردة:" in system_prompt()


def test_system_prompt_restricts_answers_to_agriculture_and_device_readings() -> None:
    prompt = system_prompt()

    assert "Only answer questions about agriculture" in prompt
    assert "Any message related to agriculture, farm devices, or device readings is in scope" in prompt
    assert "Refuse any question outside agriculture, devices, or farm/device readings" in prompt
    assert "آسف، مقدرش أرد على سؤالك , أقدر بس" in prompt
    assert "Sorry, I can't answer that." in prompt


def test_system_prompt_sets_response_language_and_blocks_pre_2026_readings() -> None:
    prompt = system_prompt()

    assert "Decide the reply language only from the text the user actually typed" in prompt
    assert "If the user's own text is fully English, reply entirely in English" in prompt
    assert "Arabic or mixed Arabic/English" in prompt
    assert "Ignore, when deciding the language" in prompt
    assert "Understand user messages in Arabic or English" in prompt
    assert "What are the latest readings?" in prompt
    assert "Give me a summary for last week" in prompt
    assert "Never answer or call tools for readings before 2026-01-01" in prompt
    assert "القراءات قبل 2026 غير متاحة." in prompt
    assert "Readings from before 2026 are not available." in prompt


def test_system_prompt_answers_capability_help_question() -> None:
    prompt = system_prompt()

    assert "تقدر تساعدني ازاي؟" in prompt
    assert "أقدر أساعدك في تلات حاجات أساسية:" in prompt
    assert "I can help you with three main things:" in prompt
    assert "تشخيص مشاكل النبات" in prompt
    assert "قراءات المزرعة" in prompt
    assert "استشارات زراعية" in prompt
    assert "Agricultural advice" in prompt


def test_system_prompt_answers_general_agriculture_questions_without_tools() -> None:
    prompt = system_prompt()

    assert "General agricultural knowledge — answer from your own knowledge, no tools" in prompt
    assert "Never refuse an agriculture question just because" in prompt
    assert "A general agriculture question never requires a tool call" in prompt
    assert "Only reach for a tool when the user asks about their own devices" in prompt
    assert "General agricultural knowledge needs no tools." in prompt


def test_system_prompt_asks_for_clarification_on_unclear_follow_ups() -> None:
    prompt = system_prompt()

    assert 'If a short follow-up like "امتى", "ازاي", "فين", or "كام" is unclear' in prompt
    assert "ask one short clarification question instead of guessing" in prompt


def test_system_prompt_uses_story_style_for_day_level_historical_answers() -> None:
    prompt = system_prompt()

    assert "answer as a short chronological story" in prompt
    assert "using the actual timestamps and readings" in prompt
    assert "Never invent events or causes" in prompt
