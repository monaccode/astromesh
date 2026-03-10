from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from collections import deque
from typing import IO, TYPE_CHECKING

from astromesh.observability.tracing import TracingContext

if TYPE_CHECKING:
    from astromesh.observability.telemetry import TelemetryManager


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


class OTLPCollector(InternalCollector):
    """Bridges TracingContext spans to OpenTelemetry via TelemetryManager."""

    def __init__(
        self,
        telemetry_manager: TelemetryManager | None = None,
        max_traces: int = 1000,
    ):
        super().__init__(max_traces=max_traces)
        self._telemetry = telemetry_manager

    async def emit_trace(self, ctx: TracingContext) -> None:
        await super().emit_trace(ctx)
        if self._telemetry and self._telemetry.get_tracer():
            tracer = self._telemetry.get_tracer()
            for span_data in ctx.to_dict().get("spans", []):
                with tracer.start_as_current_span(span_data["name"]) as otel_span:
                    for k, v in span_data.get("attributes", {}).items():
                        otel_span.set_attribute(k, v)
