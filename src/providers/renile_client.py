import logging
from datetime import date, datetime, timedelta, timezone
from time import perf_counter
from typing import Any

import httpx

from core.config import Settings

logger = logging.getLogger(__name__)


class ReNileClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.renile_api_base_url
        self._devices_path = settings.renile_devices_path
        self._current_path = settings.renile_current_readings_path
        self._historical_path = settings.renile_historical_readings_path
        self._timeout = settings.http_timeout_seconds

    async def get_current_readings(self, jwt: str) -> dict[str, Any]:
        # The backend returns this already cleaned; pass it through untouched.
        logger.info("renile_current_readings_started path=%s", self._current_path)
        response = await self._get(self._current_path, jwt, {})
        logger.info("renile_current_readings_completed")
        return response

    async def get_devices_ids(self, jwt: str) -> list[dict[str, Any]]:
        # The backend returns this already cleaned; pass it through untouched.
        logger.info("renile_devices_ids_started path=%s", self._devices_path)
        response = await self._get(self._devices_path, jwt, {})
        logger.info("renile_devices_ids_completed")
        return response

    async def get_devices_status(self, jwt: str) -> list[dict[str, Any]]:
        # Placeholder until the ReNile device-status API is ready: dummy data, no HTTP call.
        # Covers every support-flow branch: WIFI, 4G automatic, 4G manual expired and valid.
        logger.info("renile_devices_status_started source=dummy")
        now = datetime.now(timezone.utc)
        today = date.today()
        return [
            {
                "_id": "status-device-1",
                "name": "Greenhouse 1",
                "last_reading_time": (now - timedelta(minutes=5)).isoformat(timespec="seconds"),
                "readings": {"Temperature": 28.5, "Humidity": 61, "Soil_moisture": 42},
                "connection_type": "WIFI",
                "renewal_type": None,
                "renewal_date": None,
            },
            {
                "_id": "status-device-2",
                "name": "Field Station",
                "last_reading_time": (now - timedelta(days=3)).isoformat(timespec="seconds"),
                "readings": {"Temperature": None, "Humidity": 0, "Soil_moisture": None},
                "connection_type": "4G",
                "renewal_type": "automatic",
                "renewal_date": None,
            },
            {
                "_id": "status-device-3",
                "name": "Orchard Sensor",
                "last_reading_time": (now - timedelta(days=12)).isoformat(timespec="seconds"),
                "readings": {"Temperature": 30.1, "Humidity": 55},
                "connection_type": "4G",
                "renewal_type": "manual",
                "renewal_date": (today - timedelta(days=10)).isoformat(),
            },
            {
                "_id": "status-device-4",
                "name": "Nursery Unit",
                "last_reading_time": (now - timedelta(days=2)).isoformat(timespec="seconds"),
                "readings": {"Temperature": 26.4, "Humidity": 70},
                "connection_type": "4G",
                "renewal_type": "manual",
                "renewal_date": (today + timedelta(days=20)).isoformat(),
            },
        ]

    async def get_last_duration_summary(self, jwt: str, device_id: str, start_time: str) -> dict[str, Any]:
        logger.info(
            "renile_last_duration_summary_started path=%s device_id=%s start_time=%s data_type=month",
            self._historical_path,
            device_id,
            start_time,
        )
        response = await self._get(
            self._historical_path,
            jwt,
            {"data_type": "month", "start_time": start_time, "device_id": device_id},
        )
        if not isinstance(response, dict):
            logger.error("renile_last_duration_summary_invalid_shape response_type=%s", type(response).__name__)
            raise ValueError("Unexpected last duration summary response shape")
        logger.info("renile_last_duration_summary_completed sensors=%s", len(response))
        return response

    async def get_specific_time_readings(self, jwt: str, device_id: str, start_time: str) -> dict[str, Any]:
        logger.info(
            "renile_specific_time_readings_started path=%s device_id=%s start_time=%s data_type=day",
            self._historical_path,
            device_id,
            start_time,
        )
        response = await self._get(
            self._historical_path,
            jwt,
            {"data_type": "day", "start_time": start_time, "device_id": device_id},
        )
        if not isinstance(response, dict):
            logger.error("renile_specific_time_readings_invalid_shape response_type=%s", type(response).__name__)
            raise ValueError("Unexpected specific time readings response shape")
        logger.info("renile_specific_time_readings_completed sensors=%s", len(response))
        return response

    async def _get(self, path: str, jwt: str, params: dict[str, Any]) -> Any:
        started_at = perf_counter()
        headers = {"Authorization": f"JWT {jwt}"}
        safe_params = {k: v for k, v in params.items() if v is not None}
        logger.info("renile_http_get_started path=%s params=%s", path, safe_params)
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            response = await client.get(path, params=safe_params, headers=headers)
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            logger.info(
                "renile_http_get_completed path=%s status_code=%s latency_ms=%s response_bytes=%s",
                path,
                response.status_code,
                elapsed_ms,
                len(response.content),
            )
            response.raise_for_status()
            return response.json()