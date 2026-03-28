import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.core.request_context import get_request_id


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    _extra_fields = (
        "request_id",
        "query_id",
        "method",
        "path",
        "status_code",
        "duration_ms",
        "normalized_query",
        "candidate_count",
        "lexical_candidate_count",
        "vector_candidate_count",
        "strong_vector_candidate_count",
        "result_count",
        "returned_count",
        "sort",
        "retrieval_mode",
        "fallback_path",
        "limit",
        "cache_outcome",
        "source_product_id",
        "strategy_used",
        "strategy_path",
        "attempted_strategies",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field_name in self._extra_fields:
            field_value = getattr(record, field_name, None)
            if field_value is not None:
                payload[field_name] = field_value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, settings.normalized_log_level, logging.INFO))
