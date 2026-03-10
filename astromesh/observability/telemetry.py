from dataclasses import dataclass


@dataclass
class TelemetryConfig:
    service_name: str = "astromesh"
    otlp_endpoint: str = "http://localhost:4317"
    enabled: bool = True
    sample_rate: float = 1.0


class TelemetryManager:
    """OpenTelemetry tracing setup for Astromesh."""

    def __init__(self, config: TelemetryConfig | None = None):
        self._config = config or TelemetryConfig()
        self._tracer = None
        self._provider = None

    def setup(self):
        if not self._config.enabled:
            return

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            resource = Resource.create({"service.name": self._config.service_name})
            self._provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(endpoint=self._config.otlp_endpoint)
            self._provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(self._provider)
            self._tracer = trace.get_tracer(self._config.service_name)
        except ImportError:
            self._tracer = None

    def get_tracer(self):
        return self._tracer

    def trace_agent_run(self, agent_name: str, session_id: str):
        """Context manager decorator for tracing agent runs."""
        if self._tracer:
            return self._tracer.start_as_current_span(
                f"agent.run.{agent_name}",
                attributes={"agent.name": agent_name, "session.id": session_id},
            )
        return _NoOpSpan()

    def trace_provider_call(self, provider_name: str, model: str):
        if self._tracer:
            return self._tracer.start_as_current_span(
                f"provider.call.{provider_name}",
                attributes={"provider.name": provider_name, "model.name": model},
            )
        return _NoOpSpan()

    def trace_tool_execution(self, tool_name: str):
        if self._tracer:
            return self._tracer.start_as_current_span(
                f"tool.execute.{tool_name}",
                attributes={"tool.name": tool_name},
            )
        return _NoOpSpan()

    async def shutdown(self):
        if self._provider:
            self._provider.shutdown()


class _NoOpSpan:
    """No-op span for when telemetry is disabled."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def set_attribute(self, key, value):
        pass

    def add_event(self, name, attributes=None):
        pass
