import json
import sys
from abc import ABC, abstractmethod
from collections import deque
from typing import IO

from astromesh.observability.tracing import TracingContext


class Collector(ABC):
    @abstractmethod
    async def emit_trace(self, ctx: TracingContext) -> None: ...

    async def query_traces(self, agent: str | None = None, limit: int = 20) -> list[dict]:
        return []

    async def get_trace(self, trace_id: str) -> dict | None:
        return None


class StdoutCollector(Collector):
    def __init__(self, stream: IO | None = None):
        self._stream = stream or sys.stdout

    async def emit_trace(self, ctx: TracingContext) -> None:
        self._stream.write(json.dumps(ctx.to_dict(), default=str) + "\n")
        self._stream.flush()


class InternalCollector(Collector):
    """In-memory collector for development and small deployments."""

    def __init__(self, max_traces: int = 10000):
        self._traces: deque[dict] = deque(maxlen=max_traces)
        self._index: dict[str, dict] = {}

    async def emit_trace(self, ctx: TracingContext) -> None:
        trace_data = ctx.to_dict()
        self._traces.append(trace_data)
        self._index[ctx.trace_id] = trace_data

    async def query_traces(self, agent: str | None = None, limit: int = 20) -> list[dict]:
        results = list(self._traces)
        if agent:
            results = [t for t in results if t.get("agent") == agent]
        return list(reversed(results))[:limit]

    async def get_trace(self, trace_id: str) -> dict | None:
        return self._index.get(trace_id)
