import json
import logging

import pytest
from agents import FunctionTool
from agents.tool_context import ToolContext

from datetime import date

import httpx

from agent.tools import (
    SUPPORT_TOOLS,
    TOOL_FAILED_MESSAGE,
    TOOLS,
    AgentContext,
    get_current_readings,
    get_devices_ids,
    get_devices_status,
    get_last_duration_summary,
    get_specific_time_readings,
    plant_diseases_detection,
)
from conftest import FakeToolCache, build_settings
from models.schemas.chat import UploadedImage
from providers.renile_client import ReNileClient

SCHEMAS = {
    tool.name: {"description": tool.description, "parameters": tool.params_json_schema}
    for tool in TOOLS + SUPPORT_TOOLS
}


def test_tool_schemas_do_not_expose_jwt_or_runtime() -> None:
    tool_payload = json.dumps(SCHEMAS).lower()

    assert "jwt" not in tool_payload
    assert "authorization" not in tool_payload
    assert "runtime" not in tool_payload
    assert "image" not in json.dumps([schema["parameters"] for schema in SCHEMAS.values()]).lower()


def test_exposed_tool_names() -> None:
    assert {tool.name for tool in SUPPORT_TOOLS} == {"get_devices_status"}
    assert {tool.name for tool in TOOLS} == {
        "plant_diseases_detection",
        "get_current_readings",
        "get_devices_ids",
        "get_last_duration_summary",
        "get_specific_time_readings",
    }


@pytest.mark.parametrize(
    "name", ["get_current_readings", "get_devices_ids", "plant_diseases_detection", "get_devices_status"]
)
def test_argumentless_tools_have_no_agent_arguments(name: str) -> None:
    assert SCHEMAS[name]["parameters"]["properties"] == {}


@pytest.mark.parametrize("name", ["get_last_duration_summary", "get_specific_time_readings"])
def test_historical_tool_schemas_are_safe(name: str) -> None:
    parameters = SCHEMAS[name]["parameters"]

    assert parameters["required"] == ["device_id", "start_time"]
    assert set(parameters["properties"]) == {"device_id", "start_time"}
    assert "data_type" not in parameters["properties"]


BACKEND_CURRENT_READINGS = {
    "project_name": "Farm 1",
    "generated_at": "2026-08-09T12:00:00Z",
    "devices": [
        {
            "device_id": "device-1",
            "device_name": "Device 1",
            "readings": [
                {
                    "sensor": "Battery_level",
                    "value": 99,
                    "unit": "%",
                    "lower_limit": 20,
                    "upper_limit": 100,
                    "status": "normal",
                    "timestamp": "2026-06-19T10:00:00Z",
                    "age_seconds": 143,
                }
            ],
        }
    ],
}

BACKEND_DEVICES_IDS = [{"_id": "device-1", "name": "Device 1"}]

BACKEND_DEVICES_STATUS = [
    {
        "_id": "device-1",
        "name": "Device 1",
        "last_reading_time": "2026-09-23T10:00:00+00:00",
        "readings": {"Temperature": 28.5},
        "connection_type": "4G",
        "renewal_type": "manual",
        "renewal_date": "2026-09-01",
    }
]


class FakeReNileClient:
    async def get_current_readings(self, jwt: str) -> dict:
        assert jwt == "runtime-jwt"
        return BACKEND_CURRENT_READINGS

    async def get_devices_ids(self, jwt: str) -> list[dict]:
        assert jwt == "runtime-jwt"
        return BACKEND_DEVICES_IDS

    async def get_devices_status(self, jwt: str) -> list[dict]:
        assert jwt == "runtime-jwt"
        return BACKEND_DEVICES_STATUS

    async def get_last_duration_summary(self, jwt: str, device_id: str, start_time: str) -> dict:
        assert jwt == "runtime-jwt"
        assert device_id == "device-1"
        assert start_time == "2026-06-01 00:00"
        return {
            "CO2": {
                "labels": ["2026-06-01T00:00:00.000Z"],
                "data": [{"$numberDecimal": "505.94"}],
            }
        }

    async def get_specific_time_readings(self, jwt: str, device_id: str, start_time: str) -> dict:
        assert jwt == "runtime-jwt"
        assert device_id == "device-1"
        assert start_time == "2026-06-01 00:00"
        return {
            "CO2": {
                "labels": ["2026-06-01T04:00:00.000Z"],
                "data": [{"$numberDecimal": "532.55"}],
            }
        }


class FakePlantDiseaseClient:
    async def predict(self, image_bytes: bytes, filename: str, content_type: str | None) -> dict:
        assert image_bytes == b"fake-image"
        assert filename == "plant.jpg"
        assert content_type == "image/jpeg"
        return {
            "is_plant": True,
            "disease": "potato early blight",
            "is_healthy": False,
            "confidence": 0.636,
            "source": "yolo",
            "message": "نصيحة عربية",
        }


def _context(tool_cache: FakeToolCache | None = None, image: UploadedImage | None = None) -> AgentContext:
    return AgentContext(
        conversation_id="conversation-1",
        jwt="runtime-jwt",
        renile_client=FakeReNileClient(),  # type: ignore[arg-type]
        tool_cache=tool_cache or FakeToolCache(),  # type: ignore[arg-type]
        plant_disease_client=FakePlantDiseaseClient(),  # type: ignore[arg-type]
        image=image,
    )


async def invoke(tool: FunctionTool, context: AgentContext, **arguments: str) -> str:
    """Run a decorated tool the way the SDK runner does, including its failure handler."""
    tool_arguments = json.dumps(arguments)
    tool_context = ToolContext(
        context=context, tool_name=tool.name, tool_call_id="call-1", tool_arguments=tool_arguments
    )
    return await tool.on_invoke_tool(tool_context, tool_arguments)


async def test_current_readings_tool_returns_backend_response_unchanged() -> None:
    result = await invoke(get_current_readings, _context())

    assert json.loads(result) == BACKEND_CURRENT_READINGS


async def test_current_readings_tool_logs_do_not_include_jwt(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    await invoke(get_current_readings, _context())

    assert "runtime-jwt" not in caplog.text
    assert "tool_call_completed tool_name=get_current_readings" in caplog.text


async def test_current_readings_tool_caches_result_per_conversation() -> None:
    tool_cache = FakeToolCache()

    await invoke(get_current_readings, _context(tool_cache))

    assert tool_cache.stored_results == [("conversation-1", "get_current_readings", {}, BACKEND_CURRENT_READINGS)]


async def test_devices_ids_tool_returns_backend_response_unchanged() -> None:
    result = await invoke(get_devices_ids, _context())

    assert json.loads(result) == BACKEND_DEVICES_IDS


async def test_devices_status_tool_fetches_fresh_and_saves_result(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    tool_cache = FakeToolCache({("get_devices_status", "{}"): [{"_id": "stale"}]})

    result = await invoke(get_devices_status, _context(tool_cache))

    assert json.loads(result) == BACKEND_DEVICES_STATUS
    assert [(tool, arguments, stored) for _, tool, arguments, stored in tool_cache.stored_results] == [
        ("get_devices_status", {}, BACKEND_DEVICES_STATUS)
    ]
    assert "runtime-jwt" not in caplog.text


async def test_renile_devices_status_is_dummy_data_covering_every_support_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_http(*args: object, **kwargs: object) -> None:
        raise AssertionError("dummy device status must not call the ReNile API")

    monkeypatch.setattr(httpx, "AsyncClient", no_http)

    devices = await ReNileClient(build_settings()).get_devices_status("runtime-jwt")

    today = date.today().isoformat()
    branches = {(d["connection_type"], d["renewal_type"]) for d in devices}
    assert branches == {("WIFI", None), ("4G", "automatic"), ("4G", "manual")}
    manual_dates = [d["renewal_date"] for d in devices if d["renewal_type"] == "manual"]
    assert any(renewal < today for renewal in manual_dates)
    assert any(renewal >= today for renewal in manual_dates)
    assert all(d["renewal_date"] is None for d in devices if d["renewal_type"] != "manual")
    for device in devices:
        assert {"_id", "name", "last_reading_time", "readings", "connection_type"} <= device.keys()


async def test_last_duration_summary_tool_returns_processed_api_response() -> None:
    result = await invoke(
        get_last_duration_summary, _context(), device_id="device-1", start_time="2026-06-01 00:00"
    )

    assert json.loads(result) == {
        "device_id": "device-1",
        "start_time": "2026-06-01 00:00",
        "data_type": "month",
        "daily_rows": [{"date": "2026-06-01", "CO2": 505.94}],
    }


async def test_specific_time_readings_tool_returns_processed_api_response() -> None:
    result = await invoke(
        get_specific_time_readings, _context(), device_id="Device 1", start_time="2026-06-01 00:00"
    )

    assert json.loads(result) == {
        "device_id": "device-1",
        "start_time": "2026-06-01 00:00",
        "data_type": "day",
        "hourly_rows": [{"timestamp": "2026-06-01T04:00:00.000Z", "CO2": 532.55}],
    }


async def test_plant_diseases_detection_tool_returns_backend_response_unchanged() -> None:
    tool_cache = FakeToolCache()
    image = UploadedImage(filename="plant.jpg", content_type="image/jpeg", content=b"fake-image")

    context = _context(tool_cache, image=image)

    result = await invoke(plant_diseases_detection, context)

    assert json.loads(result) == {
        "is_plant": True,
        "disease": "potato early blight",
        "is_healthy": False,
        "confidence": 0.636,
        "source": "yolo",
        "message": "نصيحة عربية",
    }
    assert tool_cache.stored_results == []
    assert context.plant_prediction == json.loads(result)


async def test_plant_diseases_detection_tool_requires_an_image() -> None:
    context = _context()

    result = await invoke(plant_diseases_detection, context)

    assert result == TOOL_FAILED_MESSAGE
    assert context.plant_prediction is None
