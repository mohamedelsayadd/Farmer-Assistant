import json
import logging
from types import SimpleNamespace

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from agent.tools import (
    TOOLS,
    AgentContext,
    get_current_readings,
    get_devices_ids,
    get_last_duration_summary,
    get_specific_time_readings,
    plant_diseases_detection,
)
from conftest import FakeToolCache
from models.schemas.chat import UploadedImage

SCHEMAS = {schema["function"]["name"]: schema["function"] for schema in map(convert_to_openai_tool, TOOLS)}


def test_tool_schemas_do_not_expose_jwt_or_runtime() -> None:
    tool_payload = json.dumps(SCHEMAS).lower()

    assert "jwt" not in tool_payload
    assert "authorization" not in tool_payload
    assert "runtime" not in tool_payload
    assert "image" not in json.dumps([schema["parameters"] for schema in SCHEMAS.values()]).lower()


def test_exposed_tool_names() -> None:
    assert set(SCHEMAS) == {
        "plant_diseases_detection",
        "get_current_readings",
        "get_devices_ids",
        "get_last_duration_summary",
        "get_specific_time_readings",
    }


@pytest.mark.parametrize("name", ["get_current_readings", "get_devices_ids", "plant_diseases_detection"])
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


class FakeReNileClient:
    async def get_current_readings(self, jwt: str) -> dict:
        assert jwt == "runtime-jwt"
        return BACKEND_CURRENT_READINGS

    async def get_devices_ids(self, jwt: str) -> list[dict]:
        assert jwt == "runtime-jwt"
        return BACKEND_DEVICES_IDS

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


def _runtime(tool_cache: FakeToolCache | None = None, image: UploadedImage | None = None) -> SimpleNamespace:
    context = AgentContext(
        conversation_id="conversation-1",
        jwt="runtime-jwt",
        renile_client=FakeReNileClient(),  # type: ignore[arg-type]
        tool_cache=tool_cache or FakeToolCache(),  # type: ignore[arg-type]
        plant_disease_client=FakePlantDiseaseClient(),  # type: ignore[arg-type]
        image=image,
    )
    return SimpleNamespace(context=context)


async def test_current_readings_tool_returns_backend_response_unchanged() -> None:
    result = await get_current_readings.coroutine(runtime=_runtime())

    assert json.loads(result) == BACKEND_CURRENT_READINGS


async def test_current_readings_tool_logs_do_not_include_jwt(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    await get_current_readings.coroutine(runtime=_runtime())

    assert "runtime-jwt" not in caplog.text
    assert "tool_call_completed tool_name=get_current_readings" in caplog.text


async def test_current_readings_tool_caches_result_per_conversation() -> None:
    tool_cache = FakeToolCache()

    await get_current_readings.coroutine(runtime=_runtime(tool_cache))

    assert tool_cache.stored_results == [("conversation-1", "get_current_readings", {}, BACKEND_CURRENT_READINGS)]


async def test_devices_ids_tool_returns_backend_response_unchanged() -> None:
    result = await get_devices_ids.coroutine(runtime=_runtime())

    assert json.loads(result) == BACKEND_DEVICES_IDS


async def test_last_duration_summary_tool_returns_processed_api_response() -> None:
    result = await get_last_duration_summary.coroutine(
        device_id="device-1", start_time="2026-06-01 00:00", runtime=_runtime()
    )

    assert json.loads(result) == {
        "device_id": "device-1",
        "start_time": "2026-06-01 00:00",
        "data_type": "month",
        "daily_rows": [{"date": "2026-06-01", "CO2": 505.94}],
    }


async def test_specific_time_readings_tool_returns_processed_api_response() -> None:
    result = await get_specific_time_readings.coroutine(
        device_id="Device 1", start_time="2026-06-01 00:00", runtime=_runtime()
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

    result = await plant_diseases_detection.coroutine(runtime=_runtime(tool_cache, image=image))

    assert json.loads(result) == {
        "is_plant": True,
        "disease": "potato early blight",
        "is_healthy": False,
        "confidence": 0.636,
        "source": "yolo",
        "message": "نصيحة عربية",
    }
    assert tool_cache.stored_results == []


async def test_plant_diseases_detection_tool_requires_an_image() -> None:
    with pytest.raises(ValueError):
        await plant_diseases_detection.coroutine(runtime=_runtime())
