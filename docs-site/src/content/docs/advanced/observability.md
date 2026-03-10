---
title: Observability Stack
description: Tracing, metrics, and cost tracking
---

Astromesh provides built-in observability across three pillars: distributed tracing (OpenTelemetry), metrics (Prometheus), and cost tracking. All three are optional and degrade gracefully when their dependencies are not installed.

## Architecture

```
Agent Execution --> TelemetryManager --> OpenTelemetry Collector --> Jaeger / Zipkin
                         |
                    MetricsCollector --> Prometheus --> Grafana
                         |
                    CostTracker --> Usage records + budget alerts
```

Each component operates independently. You can use tracing without metrics, metrics without cost tracking, or any combination.

## Installing Dependencies

The observability dependencies are bundled in the `observability` extra:

```bash
uv sync --extra observability
```

This installs:

- `opentelemetry-api` (>= 1.27.0)
- `opentelemetry-sdk` (>= 1.27.0)
- `opentelemetry-exporter-otlp` (>= 1.27.0)
- `prometheus-client` (>= 0.21.0)

If these packages are not installed, Astromesh uses no-op fallbacks and logs no warnings.

## Tracing (OpenTelemetry)

### Configuration

Set the OTLP endpoint via environment variable or `TelemetryConfig`:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

The `TelemetryManager` initializes on startup:

```python
from astromesh.observability.telemetry import TelemetryManager, TelemetryConfig

telemetry = TelemetryManager(TelemetryConfig(
    service_name="astromesh",
    otlp_endpoint="http://localhost:4317",
    enabled=True,
    sample_rate=1.0,
))
telemetry.setup()
```

### What Gets Traced

Three span types are created during agent execution:

| Span Name | Attributes | Description |
|-----------|-----------|-------------|
| `agent.run.<name>` | `agent.name`, `session.id` | Full agent execution from query to response |
| `provider.call.<provider>` | `provider.name`, `model.name` | Individual LLM provider call |
| `tool.execute.<tool>` | `tool.name` | Tool execution within an orchestration step |

Spans are nested: an `agent.run` span contains one or more `provider.call` spans, which may contain `tool.execute` spans (in tool-calling flows like ReAct).

### NoOpSpan Fallback

When OpenTelemetry is not installed, `TelemetryManager` returns `_NoOpSpan` instances. These implement `__enter__`, `__exit__`, `set_attribute`, and `add_event` as no-ops. No code changes are needed — the tracing context managers work identically whether OTel is present or not.

### Lightweight Tracing (TracingContext)

In addition to full OpenTelemetry export, Astromesh includes a lightweight built-in tracing system that works without any external dependencies. Every agent run automatically collects spans into a `TracingContext`:

```python
from astromesh.observability.tracing import TracingContext

ctx = TracingContext(agent_name="my-agent", session_id="sess_123")
span = ctx.start_span("agent.run", {"agent": "my-agent"})

# Nested spans
child = ctx.start_span("llm.complete", parent_span_id=span.span_id)
child.set_attribute("input_tokens", 150)
ctx.finish_span(child)

ctx.finish_span(span)
trace_data = ctx.to_dict()
```

**Automatic spans in Agent.run():**

Every call to `Agent.run()` produces these spans automatically:

| Span Name | Parent | Attributes | Description |
|-----------|--------|-----------|-------------|
| `agent.run` | (root) | `agent`, `session` | Full execution lifecycle |
| `memory_build` | `agent.run` | — | Build memory context |
| `prompt_render` | `agent.run` | — | Render Jinja2 prompt |
| `llm.complete` | `agent.run` | `input_tokens`, `output_tokens` | Each LLM call |
| `tool.call` | `agent.run` | `tool` | Each tool execution |
| `orchestration` | `agent.run` | `pattern` | Orchestration pattern execution |
| `memory_persist` | `agent.run` | — | Persist conversation turns |

The trace is attached to the agent response:

```json
{
  "answer": "...",
  "trace": {
    "trace_id": "abc123",
    "agent": "my-agent",
    "spans": [
      {
        "name": "agent.run",
        "span_id": "s1",
        "start_time": "2026-03-10T...",
        "end_time": "2026-03-10T...",
        "duration_ms": 2340,
        "attributes": {"agent": "my-agent"},
        "status": "OK"
      }
    ]
  }
}
```

**Trace Collectors:**

Traces are stored via pluggable collectors:

| Collector | Use Case | Storage |
|-----------|----------|---------|
| `StdoutCollector` | Development/debugging | Writes JSON to stdout |
| `InternalCollector` | Small deployments | In-memory deque (default 10K traces) |
| `OTLPCollector` | Production | In-memory + bridges to OpenTelemetry via TelemetryManager |

```python
from astromesh.observability.collector import InternalCollector, OTLPCollector
from astromesh.observability.telemetry import TelemetryManager

# Development: in-memory only
collector = InternalCollector(max_traces=10000)

# Production: in-memory + OTel export
telemetry = TelemetryManager()
telemetry.setup()
collector = OTLPCollector(telemetry_manager=telemetry)
```

### Viewing Traces

Send traces to any OpenTelemetry-compatible backend:

- **Jaeger** — `docker run -p 16686:16686 jaegertracing/all-in-one:latest`
- **Zipkin** — `docker run -p 9411:9411 openzipkin/zipkin`
- **Grafana Tempo** — included in the `dev-full` Docker recipe

Open the backend UI and search by service name `astromesh` to see agent execution traces with timing breakdowns.

### Traces API

Query collected traces via REST:

**List traces:**
```
GET /v1/traces/?agent=my-agent&limit=20
```

```json
{
  "traces": [
    {
      "trace_id": "abc123",
      "agent": "my-agent",
      "spans": [...]
    }
  ]
}
```

**Get specific trace:**
```
GET /v1/traces/{trace_id}
```

Returns 404 if not found.

## Metrics (Prometheus)

### Exposed Metrics

The `MetricsCollector` registers the following Prometheus metrics with the configurable prefix `astromesh` (default):

#### Counters

| Metric | Labels | Description |
|--------|--------|-------------|
| `astromesh_agent_runs_total` | `agent_name`, `pattern`, `status` | Total agent executions |
| `astromesh_provider_calls_total` | `provider`, `model`, `status` | Total LLM provider calls |
| `astromesh_tool_executions_total` | `tool_name`, `status` | Total tool executions |
| `astromesh_tokens_used_total` | `agent_name`, `direction` | Total tokens consumed (direction: `input` or `output`) |

#### Histograms

| Metric | Labels | Description |
|--------|--------|-------------|
| `astromesh_agent_latency_seconds` | `agent_name`, `pattern` | Agent run latency distribution |
| `astromesh_provider_latency_seconds` | `provider`, `model` | Provider call latency distribution |

#### Gauges

| Metric | Labels | Description |
|--------|--------|-------------|
| `astromesh_active_sessions` | `agent_name` | Currently active sessions per agent |

### Scrape Endpoint

When `prometheus-client` is installed, metrics are exposed on the default Prometheus client HTTP server. In Kubernetes, pods are auto-annotated for Prometheus scraping.

Configure your `prometheus.yml` scrape target:

```yaml
scrape_configs:
  - job_name: "astromesh"
    static_configs:
      - targets: ["astromesh:8000"]
    metrics_path: "/metrics"
    scrape_interval: 15s
```

### PromQL Examples

Common queries for dashboards and alerts:

```promql
# Agent runs per minute by agent
rate(astromesh_agent_runs_total[1m])

# P95 agent latency
histogram_quantile(0.95, rate(astromesh_agent_latency_seconds_bucket[5m]))

# Error rate by agent
rate(astromesh_agent_runs_total{status="error"}[5m])
  / rate(astromesh_agent_runs_total[5m])

# Token consumption per hour by agent
increase(astromesh_tokens_used_total[1h])

# Provider latency P99
histogram_quantile(0.99, rate(astromesh_provider_latency_seconds_bucket[5m]))

# Currently active sessions across all agents
sum(astromesh_active_sessions)
```

## Cost Tracking

The `CostTracker` records per-call usage and enforces budgets. It does not require any external dependencies (it is part of the core Astromesh package).

### Usage Records

Every LLM provider call generates a `UsageRecord`:

```python
@dataclass
class UsageRecord:
    agent_name: str
    session_id: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    pattern: str
    timestamp: datetime
```

Records are stored in memory and can be queried with optional filters:

```python
tracker.get_total_cost(agent_name="support-agent")
tracker.get_total_cost(agent_name="support-agent", since=one_hour_ago)
tracker.get_usage_summary(agent_name="support-agent")
```

### Budget Enforcement

Set a maximum spend per agent:

```python
tracker.set_budget("support-agent", max_usd=10.0)

result = tracker.check_budget("support-agent")
# {
#     "has_budget": True,
#     "budget": 10.0,
#     "spent": 3.42,
#     "remaining": 6.58,
#     "exceeded": False
# }
```

When the budget is exceeded, `check_budget()` returns `exceeded: True`. The runtime can use this to reject further requests for that agent.

### Cost Reports

The `get_usage_summary()` method returns a detailed breakdown:

```python
tracker.get_usage_summary(agent_name="support-agent")
# {
#     "total_cost": 3.42,
#     "total_input_tokens": 125000,
#     "total_output_tokens": 42000,
#     "total_tokens": 167000,
#     "num_calls": 85,
#     "avg_latency_ms": 1250.5,
#     "by_provider": {
#         "openai": {"cost": 2.10, "calls": 50, "tokens": 100000},
#         "anthropic": {"cost": 1.32, "calls": 35, "tokens": 67000}
#     },
#     "by_model": {
#         "gpt-4o-mini": {"cost": 1.05, "calls": 40, "tokens": 80000},
#         "gpt-4o": {"cost": 1.05, "calls": 10, "tokens": 20000},
#         "claude-sonnet-4-20250514": {"cost": 1.32, "calls": 35, "tokens": 67000}
#     }
# }
```

When Rust native extensions are compiled, cost aggregation uses `RustCostIndex` for faster queries over large record sets. See the [Rust Native Extensions](/astromesh/advanced/rust-extensions/) guide.

## Metrics API

In addition to Prometheus metrics, Astromesh provides a simple REST API for in-memory counters and histograms:

**Get current metrics:**
```
GET /v1/metrics/
```

```json
{
  "counters": {
    "agent.runs": 150,
    "tool.executions": 420
  },
  "histograms": {
    "agent.latency_ms": {
      "count": 150,
      "sum": 345000,
      "avg": 2300,
      "min": 450,
      "max": 8900
    }
  }
}
```

**Reset all metrics:**
```
POST /v1/metrics/reset
```

These metrics are stored in memory and reset on daemon restart. For persistent metrics, use the Prometheus integration described above.

## Docker Setup

The `recipes/dev-full.yml` Docker Compose file includes a complete observability stack:

```bash
docker compose -f recipes/dev-full.yml up -d
```

This starts:

| Service | URL | Purpose |
|---------|-----|---------|
| Astromesh | `http://localhost:8000` | Agent runtime |
| OTel Collector | `localhost:4317` (gRPC), `localhost:4318` (HTTP) | Receives traces and forwards to backends |
| Prometheus | `http://localhost:9090` | Metrics storage and querying |
| Grafana | `http://localhost:3000` | Dashboards and visualization |

The OTel Collector is pre-configured via `docker/otel-config.yaml` to receive OTLP traces and export them to the configured backend.

### Grafana

Access Grafana at `http://localhost:3000` with default credentials:

- **Username:** `admin`
- **Password:** `admin`

To create a dashboard:

1. Go to Dashboards > New > New Dashboard
2. Add a panel and select Prometheus as the data source
3. Use the PromQL queries from the section above
4. Recommended panels:
   - **Agent Runs/min** — time series with `rate(astromesh_agent_runs_total[1m])`
   - **P95 Latency** — time series with `histogram_quantile(0.95, ...)`
   - **Active Sessions** — gauge with `sum(astromesh_active_sessions)`
   - **Token Usage** — stacked bar with `increase(astromesh_tokens_used_total[1h])`
   - **Error Rate** — stat panel with the error rate query

## Kubernetes Setup

For Kubernetes deployments using the Astromesh Helm chart, enable the observability subcharts:

```yaml
# values.yaml
kube-prometheus-stack:
  enabled: true

opentelemetry-collector:
  enabled: true
```

When the OTel Collector subchart is enabled, the Astromesh deployment is automatically configured with the correct OTLP endpoint via the `astromesh.otel.endpoint` Helm helper. No manual endpoint configuration is needed.

The `kube-prometheus-stack` subchart bundles:

- Prometheus server with auto-discovery of annotated pods
- Grafana with the Prometheus data source pre-configured
- Alertmanager for alert routing

For production clusters that already have a Prometheus and Grafana deployment, leave the subcharts disabled and point Astromesh to your existing OTel Collector endpoint:

```yaml
# values.yaml
kube-prometheus-stack:
  enabled: false

opentelemetry-collector:
  enabled: false

observability:
  otel:
    endpoint: "otel-collector.monitoring.svc.cluster.local:4317"
```
