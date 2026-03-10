import json
import sys
from datetime import datetime, timezone
from typing import IO, Any


class StructuredLogger:
    """JSON structured logger for Astromesh events."""

    def __init__(self, stream: IO | None = None):
        self._stream = stream or sys.stdout

    def _emit(self, level: str, event: str, **kwargs: Any):
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            **kwargs,
        }
        self._stream.write(json.dumps(record, default=str) + "\n")
        self._stream.flush()

    def info(self, event: str, **kwargs):
        self._emit("info", event, **kwargs)

    def warning(self, event: str, **kwargs):
        self._emit("warning", event, **kwargs)

    def error(self, event: str, **kwargs):
        self._emit("error", event, **kwargs)

    def debug(self, event: str, **kwargs):
        self._emit("debug", event, **kwargs)
