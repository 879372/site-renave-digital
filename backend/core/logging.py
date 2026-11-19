import json
import logging
from datetime import UTC, datetime

from .context import organization_id_var, request_id_var, user_id_var


class RequestIDFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        record.user_id = user_id_var.get()
        record.organization_id = organization_id_var.get()
        return True


class JSONFormatter(logging.Formatter):
    """Log estruturado em JSON. Nunca registre PII sem passar por core.masking."""

    def format(self, record):
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "user_id": getattr(record, "user_id", "-"),
            "organization_id": getattr(record, "organization_id", "-"),
        }
        extra = getattr(record, "data", None)
        if isinstance(extra, dict):
            payload["data"] = extra
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)
