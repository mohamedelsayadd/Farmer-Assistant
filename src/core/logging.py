import logging
import json
from typing import Any


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def json_preview(payload: Any, max_chars: int = 4000) -> str:
    serialized_payload = json.dumps(payload, ensure_ascii=False, default=str)
    if len(serialized_payload) <= max_chars:
        return serialized_payload
    return f"{serialized_payload[:max_chars]}...<truncated>"
