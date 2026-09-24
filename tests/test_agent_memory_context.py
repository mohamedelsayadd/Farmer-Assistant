from agent.agent import build_messages, support_prompt, system_prompt
from agent.prompts import SYSTEM_PROMPT
from agent.support_prompts import SUPPORT_PROMPT


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


def test_system_prompt_hands_off_only_explicit_support_problems() -> None:
    prompt = system_prompt()

    assert "# Customer Support Handoff" in prompt
    assert "The user explicitly reports or complains about a problem with a device" in prompt
    assert "A support conversation already started in the conversation history" in prompt
    assert "answers the support agent's last question" in prompt
    assert "Never start a support transfer because a tool result looks stale, missing, abnormal, or suspicious" in prompt
    assert "Requests for current or past readings always stay with you" in prompt


def test_farmer_and_support_prompts_are_separate() -> None:
    assert SUPPORT_PROMPT not in SYSTEM_PROMPT
    assert "# ReNile Customer Support" not in system_prompt()
    assert "# ReNile Assistant" not in support_prompt()


def test_support_prompt_hands_non_support_messages_back_to_farmer() -> None:
    prompt = support_prompt()

    assert "# Leaving Support" in prompt
    assert "Transfer back to the Farmer Assistant, without answering yourself" in prompt
    assert "after the flow already ended with the Final Support Reply or the Recharge Reply" in prompt
    assert "Short answers to your last support question" in prompt
    assert "never transfer those back" in prompt


def test_support_prompt_identifies_device_before_status_check() -> None:
    prompt = support_prompt()

    assert "Today's date:" in prompt
    assert "If the user mentioned the device name or ID, immediately call get_devices_status" in prompt
    assert "Do not call get_devices_status until the device is identified" in prompt
    assert "ممكن تقولي اسم الجهاز أو رقمه؟" in prompt
    assert "Never guess." in prompt


def test_support_prompt_sensor_problem_skips_connection_and_power_checks() -> None:
    prompt = support_prompt()

    assert "A. Sensor problem" in prompt
    assert "Do NOT ask about WiFi, renewal, power, or the indicator light" in prompt
    assert "If the tool result confirms the missing or abnormal reading, immediately reply with the Final Support Reply" in prompt
    assert "B. Device problem" in prompt


def test_support_prompt_orders_connection_checks_before_power() -> None:
    prompt = support_prompt()

    steps = ["# Step 1.", "# Step 2.", "# Step 3. WIFI device", "# Step 4. 4G device", "# Step 5. Power check", "# Step 6."]
    positions = [prompt.index(step) for step in steps]
    assert positions == sorted(positions)
    assert "same username and password that the device was previously connected to" in prompt
    assert "Do not ask about power before this question is answered" in prompt
    assert 'renewal_type "automatic": skip the renewal-date check and continue to Step 5' in prompt
    assert "If the renewal date has passed, reply with the Recharge Reply. STOP the flow." in prompt
    assert "Is the device receiving power properly, and is the indicator light on?" in prompt
    assert "Only if the user confirms BOTH" in prompt


def test_support_prompt_strict_rules() -> None:
    prompt = support_prompt()

    for rule in [
        "Follow the steps in exactly this order.",
        "Never perform the power check before the WIFI/4G checks required above.",
        "Never perform WIFI checks for a 4G device.",
        "Never perform renewal checks for WIFI devices.",
        "Never ask about WIFI or power for a confirmed sensor-only problem.",
        "tool results alone must never start a support flow",
        "continue it across turns using the conversation history and the previous support question",
    ]:
        assert rule in prompt


def test_support_prompt_has_fixed_replies_in_both_languages() -> None:
    prompt = support_prompt()

    assert "فريق الدعم الفني هيتواصل معاك في أقرب وقت." in prompt
    assert "Technical support will contact you as soon as possible." in prompt
    assert "تاريخ تجديد باقة الجهاز انتهى، ومحتاج تشحن الباقة." in prompt
    assert "The renewal date has expired. You need to recharge the package." in prompt
    assert "Decide the reply language only from the text the user actually typed" in prompt
