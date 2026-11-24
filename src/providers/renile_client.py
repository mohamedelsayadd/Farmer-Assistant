import logging
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
        self._devices_summary_path = settings.renile_devices_summary_path
        self._complaints_path = settings.renile_complaints_path
        self._complaints_api_key = settings.renile_complaints_api_key
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

    async def get_devices_status(self, jwt: str) -> dict[str, Any]:
        logger.info("renile_devices_status_started path=%s", self._devices_summary_path)
        response = await self._get(self._devices_summary_path, jwt, {})
        if not isinstance(response, dict) or not isinstance(response.get("devices"), list):
            logger.error("renile_devices_status_invalid_shape response_type=%s", type(response).__name__)
            raise ValueError("Unexpected devices status response shape")
        logger.info("renile_devices_status_completed devices=%s", len(response["devices"]))
        return response

    async def create_complaint(self, device_id: str, name: str, phone: str, description: str) -> dict[str, Any]:
        # Authenticated by the service API key, not the user's JWT. Never retried: a retry could duplicate the complaint.
        started_at = perf_counter()
        body = {"device_id": device_id, "name": name, "phone": phone, "description": description}
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            response = await client.post(
                self._complaints_path, json=body, headers={"x-api-key": self._complaints_api_key}
            )
        logger.info(
            "renile_complaint_completed path=%s device_id=%s status_code=%s latency_ms=%s",
            self._complaints_path,
            device_id,
            response.status_code,
            int((perf_counter() - started_at) * 1000),
        )
        response.raise_for_status()
        return response.json()

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