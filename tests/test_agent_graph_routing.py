from types import SimpleNamespace

from agent.graph import FarmerAssistantAgent


def test_tool_path_routes_current_readings() -> None:
    state = {"assistant_message": _assistant_message("get_current_readings")}

    assert FarmerAssistantAgent._tool_path(state) == "current_tools"


def test_tool_path_routes_devices_ids_to_historical_path() -> None:
    state = {"assistant_message": _assistant_message("get_devices_ids")}

    assert FarmerAssistantAgent._tool_path(state) == "historical_tools"


def test_tool_path_routes_last_duration_summary_to_historical_path() -> None:
    state = {"assistant_message": _assistant_message("get_last_duration_summary")}

    assert FarmerAssistantAgent._tool_path(state) == "historical_tools"


def test_tool_path_routes_specific_time_readings_to_historical_path() -> None:
    state = {"assistant_message": _assistant_message("get_specific_time_readings")}

    assert FarmerAssistantAgent._tool_path(state) == "historical_tools"


def test_tool_path_routes_no_tool_calls_to_final() -> None:
    state = {"assistant_message": SimpleNamespace(tool_calls=[])}

    assert FarmerAssistantAgent._tool_path(state) == "final"


def _assistant_message(tool_name: str) -> SimpleNamespace:
    return SimpleNamespace(
        tool_calls=[SimpleNamespace(function=SimpleNamespace(name=tool_name))],
    )
