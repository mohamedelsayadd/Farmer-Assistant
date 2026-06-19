from agent.tools import OPENAI_TOOLS


def test_tool_schemas_do_not_expose_jwt() -> None:
    tool_payload = str(OPENAI_TOOLS).lower()

    assert "jwt" not in tool_payload
    assert "authorization" not in tool_payload
