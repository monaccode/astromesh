from dataclasses import dataclass


@dataclass
class MetricsConfig:
    enabled: bool = True
    prefix: str = "astromesh"


class MetricsCollector:
    """Prometheus metrics for Astromesh agent runs."""

    def __init__(self, config: MetricsConfig | None = None):
        self._config = config or MetricsConfig()
        self._counters = {}
        self._histograms = {}
        self._gauges = {}

        if self._config.enabled:
            self._setup_metrics()

    def _setup_metrics(self):
        try:
            from prometheus_client import Counter, Histogram, Gauge

            prefix = self._config.prefix
            self._counters["agent_runs"] = Counter(
                f"{prefix}_agent_runs_total",
                "Total agent runs",
                ["agent_name", "pattern", "status"],
            )
            self._counters["provider_calls"] = Counter(
                f"{prefix}_provider_calls_total",
                "Total provider calls",
                ["provider", "model", "status"],
            )
            self._counters["tool_executions"] = Counter(
                f"{prefix}_tool_executions_total",
                "Total tool executions",
                ["tool_name", "status"],
            )
            self._counters["tokens_used"] = Counter(
                f"{prefix}_tokens_used_total",
                "Total tokens used",
                ["agent_name", "direction"],  # direction: input/output
            )
            self._histograms["agent_latency"] = Histogram(
                f"{prefix}_agent_latency_seconds",
                "Agent run latency",
                ["agent_name", "pattern"],
            )
            self._histograms["provider_latency"] = Histogram(
                f"{prefix}_provider_latency_seconds",
                "Provider call latency",
                ["provider", "model"],
            )
            self._gauges["active_sessions"] = Gauge(
                f"{prefix}_active_sessions",
                "Currently active sessions",
                ["agent_name"],
            )
        except ImportError:
            pass

    def record_agent_run(self, agent_name: str, pattern: str, status: str, latency_s: float):
        if "agent_runs" in self._counters:
            self._counters["agent_runs"].labels(agent_name=agent_name, pattern=pattern, status=status).inc()
        if "agent_latency" in self._histograms:
            self._histograms["agent_latency"].labels(agent_name=agent_name, pattern=pattern).observe(latency_s)

    def record_provider_call(self, provider: str, model: str, status: str, latency_s: float):
        if "provider_calls" in self._counters:
            self._counters["provider_calls"].labels(provider=provider, model=model, status=status).inc()
        if "provider_latency" in self._histograms:
            self._histograms["provider_latency"].labels(provider=provider, model=model).observe(latency_s)

    def record_tool_execution(self, tool_name: str, status: str):
        if "tool_executions" in self._counters:
            self._counters["tool_executions"].labels(tool_name=tool_name, status=status).inc()

    def record_tokens(self, agent_name: str, input_tokens: int, output_tokens: int):
        if "tokens_used" in self._counters:
            self._counters["tokens_used"].labels(agent_name=agent_name, direction="input").inc(input_tokens)
            self._counters["tokens_used"].labels(agent_name=agent_name, direction="output").inc(output_tokens)

    def set_active_sessions(self, agent_name: str, count: int):
        if "active_sessions" in self._gauges:
            self._gauges["active_sessions"].labels(agent_name=agent_name).set(count)
