import logging
from time import perf_counter
from typing import Any

import httpx

from core.config import Settings

logger = logging.getLogger(__name__)


class ReNileClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.renile_api_base_url
        self._current_path = settings.renile_current_readings_path
        self._historical_path = settings.renile_historical_readings_path
        self._timeout = settings.http_timeout_seconds

    async def get_current_readings(self, jwt: str) -> list[dict[str, Any]]:
        logger.info("renile_current_readings_started path=%s", self._current_path)
        response = await self._get(self._current_path, jwt, {})
        if not isinstance(response, list):
            logger.error("renile_current_readings_invalid_shape response_type=%s", type(response).__name__)
            raise ValueError("Unexpected current readings response shape")
        logger.info("renile_current_readings_completed devices=%s", len(response))
        return response

    async def get_historical_readings(self, jwt: str, params: dict[str, Any]) -> dict[str, Any]:
        return await self._get(self._historical_path, jwt, params)

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
