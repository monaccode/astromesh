"""Fase 4.4c: per-agent egress byte attribution exported as OTLP metrics.

App-side (the engine knows which agent makes each provider call), reusing the same OTLP endpoint as the
traces (4.3). Off by default; enabled only when observability.otlp.enabled.
"""

import os
from dataclasses import dataclass


@dataclass
class MetricsConfig:
    endpoint: str = "http://127.0.0.1:4317"
    enabled: bool = False

    @classmethod
    def from_env_and_dict(cls, observability: dict) -> "MetricsConfig":
        otlp = (observability or {}).get("otlp", {}) or {}
        endpoint = (
            otlp.get("endpoint")
            or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
            or "http://127.0.0.1:4317"
        )
        return cls(endpoint=endpoint, enabled=bool(otlp.get("enabled", False)))


class MetricsManager:
    def __init__(self, endpoint: str = "http://127.0.0.1:4317", enabled: bool = False):
        self._endpoint = endpoint
        self._enabled = enabled
        self._provider = None
        self._counter = None  # 4.4c: astromesh.agent.egress.bytes
        self._runs = None  # 4.3b: engine-derived instruments
        self._latency = None
        self._llm_calls = None
        self._llm_latency = None
        self._tokens = None
        self._cost = None
        self._tools = None

    def setup(self):
        if not self._enabled:
            return
        try:
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            from opentelemetry.sdk.resources import Resource

            exporter = OTLPMetricExporter(endpoint=self._endpoint)
            reader = PeriodicExportingMetricReader(exporter, export_interval_millis=3_600_000)
            self._provider = MeterProvider(
                resource=Resource.create({"service.name": "astromesh"}),
                metric_readers=[reader],
            )
            meter = self._provider.get_meter("astromesh.agent")
            self._counter = meter.create_counter("astromesh.agent.egress.bytes", unit="By")
            # 4.3b: full engine metric set, derived per-run from the TracingContext.
            self._runs = meter.create_counter("astromesh.agent.runs", unit="1")
            self._latency = meter.create_histogram("astromesh.agent.latency", unit="s")
            self._llm_calls = meter.create_counter("astromesh.llm.calls", unit="1")
            self._llm_latency = meter.create_histogram("astromesh.llm.latency", unit="s")
            self._tokens = meter.create_counter("astromesh.agent.tokens", unit="1")
            self._cost = meter.create_counter("astromesh.agent.cost", unit="USD")
            self._tools = meter.create_counter("astromesh.tool.executions", unit="1")
        except Exception:
            import logging

            logging.getLogger("astromeshd").warning("agent metrics unavailable", exc_info=True)
            self._counter = None
            self._runs = self._latency = self._llm_calls = self._llm_latency = None
            self._tokens = self._cost = self._tools = None

    def record(self, agent: str, model: str, nbytes: int) -> None:
        if self._counter is not None and nbytes > 0:
            try:
                self._counter.add(nbytes, {"agent": agent, "model": model or "unknown"})
            except Exception:
                pass

    def record_run(self, ctx) -> None:
        """4.3b: derive the engine metric set from a completed TracingContext. Best-effort; never raises."""
        try:
            spans = getattr(ctx, "spans", None) or []
            agent_name = getattr(ctx, "agent_name", "unknown")
            for s in spans:
                name = getattr(s, "name", "")
                attrs = getattr(s, "attributes", {}) or {}
                status = getattr(getattr(s, "status", None), "value", "unknown")
                if name == "agent.run":
                    ag = attrs.get("agent", agent_name)
                    if self._runs is not None:
                        self._runs.add(1, {"agent": ag, "status": status})
                    dur = getattr(s, "duration_ms", None)
                    if dur is not None and self._latency is not None:
                        self._latency.record(float(dur) / 1000.0, {"agent": ag})
                elif name == "llm.complete":
                    provider = attrs.get("provider", "unknown")
                    model = attrs.get("model", "unknown")
                    if self._llm_calls is not None:
                        self._llm_calls.add(
                            1, {"provider": provider, "model": model, "status": status}
                        )
                    lat = attrs.get("latency_ms")
                    if lat is not None and self._llm_latency is not None:
                        self._llm_latency.record(
                            float(lat) / 1000.0, {"provider": provider, "model": model}
                        )
                    it = int(attrs.get("input_tokens", 0) or 0)
                    ot = int(attrs.get("output_tokens", 0) or 0)
                    if self._tokens is not None:
                        if it > 0:
                            self._tokens.add(it, {"agent": agent_name, "direction": "input"})
                        if ot > 0:
                            self._tokens.add(ot, {"agent": agent_name, "direction": "output"})
                    cost = float(attrs.get("cost", 0.0) or 0.0)
                    if cost > 0 and self._cost is not None:
                        self._cost.add(cost, {"agent": agent_name, "model": model})
                elif name == "tool.call":
                    tool = attrs.get("tool", "unknown")
                    if self._tools is not None:
                        self._tools.add(1, {"tool": tool, "status": status})
        except Exception:
            pass

    def flush(self, timeout_millis: int = 5000) -> None:
        if self._provider is not None:
            try:
                self._provider.force_flush(timeout_millis=timeout_millis)
            except Exception:
                pass


_manager: "MetricsManager | None" = None


def set_manager(m: "MetricsManager | None") -> None:
    global _manager
    _manager = m


def get_manager() -> "MetricsManager | None":
    return _manager
