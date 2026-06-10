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
        self._counter = None

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
        except Exception:
            import logging
            logging.getLogger("astromeshd").warning("agent-egress metrics unavailable", exc_info=True)
            self._counter = None

    def record(self, agent: str, model: str, nbytes: int) -> None:
        if self._counter is not None and nbytes > 0:
            try:
                self._counter.add(nbytes, {"agent": agent, "model": model or "unknown"})
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
