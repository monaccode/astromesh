"""Fase 4.3: OTLP export activation — config precedence + engine emits traces to the active collector."""

import pytest

from astromesh.observability.telemetry import TelemetryConfig


def test_endpoint_from_env(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.example:4317")
    cfg = TelemetryConfig.from_env_and_dict({})
    assert cfg.otlp_endpoint == "http://collector.example:4317"
    # env alone does not enable export — only observability.otlp.enabled does.
    assert cfg.enabled is False


def test_endpoint_dict_overrides_default(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    cfg = TelemetryConfig.from_env_and_dict(
        {"otlp": {"endpoint": "http://x:4317", "enabled": True}}
    )
    assert cfg.otlp_endpoint == "http://x:4317"
    assert cfg.enabled is True


def test_endpoint_default(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    cfg = TelemetryConfig.from_env_and_dict({})
    assert cfg.otlp_endpoint == "http://localhost:4317"
    assert cfg.enabled is False


@pytest.fixture
def otel_config_dir(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test-agent.agent.yaml").write_text(
        """
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: test-agent
  version: "0.1.0"
  namespace: test
spec:
  identity:
    display_name: "Test Agent"
    description: "A test agent"
  model:
    primary:
      provider: ollama
      model: "llama3:8b"
      endpoint: "http://127.0.0.1:1/v1"
  prompts:
    system: "You are a test agent."
  orchestration:
    pattern: react
    max_iterations: 2
"""
    )
    return str(tmp_path)


async def test_engine_emits_trace_to_collector(otel_config_dir):
    """A run whose LLM call fails (unreachable provider) must STILL emit the pre-LLM spans to the
    active collector — the emit is in `engine.run`'s `finally`."""
    from astromesh.runtime.engine import AgentRuntime
    from astromesh.api.routes import traces as traces_route
    from astromesh.observability.collector import InternalCollector

    coll = InternalCollector()
    traces_route.set_collector(coll)

    runtime = AgentRuntime(config_dir=otel_config_dir)
    await runtime.bootstrap()
    try:
        await runtime.run("test-agent", "hello", "s1")
    except Exception:
        pass  # provider is unreachable; we only care that the trace was emitted

    traces = await coll.query_traces(limit=10)
    span_names = [s.get("name") for t in traces for s in t.get("spans", [])]
    assert "agent.run" in span_names


def test_enabled_from_astromesh_env(monkeypatch):
    """ASTROMESH_OTLP_ENABLED turns export on when the dict says nothing."""
    monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", "1")
    assert TelemetryConfig.from_env_and_dict({}).enabled is True


def test_enabled_env_truthy_variants(monkeypatch):
    for value in ("1", "true", "TRUE", "yes", " Yes "):
        monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", value)
        assert TelemetryConfig.from_env_and_dict({}).enabled is True, value


def test_enabled_env_falsy_variants(monkeypatch):
    for value in ("0", "false", "no", ""):
        monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", value)
        assert TelemetryConfig.from_env_and_dict({}).enabled is False, value


def test_dict_enabled_false_beats_env(monkeypatch):
    """An explicit dict value wins over the env var, even when it disables export."""
    monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", "1")
    assert TelemetryConfig.from_env_and_dict({"otlp": {"enabled": False}}).enabled is False


def test_metrics_config_enabled_from_astromesh_env(monkeypatch):
    from astromesh.observability.metrics_export import MetricsConfig

    monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", "1")
    assert MetricsConfig.from_env_and_dict({}).enabled is True


def test_metrics_config_dict_enabled_false_beats_env(monkeypatch):
    from astromesh.observability.metrics_export import MetricsConfig

    monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", "1")
    assert MetricsConfig.from_env_and_dict({"otlp": {"enabled": False}}).enabled is False
