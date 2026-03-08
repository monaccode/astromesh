from astromesh.observability.telemetry import TelemetryManager, TelemetryConfig, _NoOpSpan
from astromesh.observability.metrics import MetricsCollector, MetricsConfig
from astromesh.observability.cost_tracker import CostTracker, UsageRecord


def test_telemetry_disabled():
    config = TelemetryConfig(enabled=False)
    mgr = TelemetryManager(config)
    mgr.setup()
    assert mgr.get_tracer() is None


def test_telemetry_noop_span():
    span = _NoOpSpan()
    with span:
        span.set_attribute("key", "value")
        span.add_event("test")


def test_trace_agent_run_no_tracer():
    mgr = TelemetryManager(TelemetryConfig(enabled=False))
    mgr.setup()
    span = mgr.trace_agent_run("test-agent", "session1")
    assert isinstance(span, _NoOpSpan)


def test_metrics_disabled():
    config = MetricsConfig(enabled=False)
    collector = MetricsCollector(config)
    # Should not raise
    collector.record_agent_run("test", "react", "success", 0.5)
    collector.record_provider_call("ollama", "llama3", "success", 0.1)
    collector.record_tool_execution("search", "success")
    collector.record_tokens("test", 100, 50)


def test_cost_tracker_record():
    tracker = CostTracker()
    record = UsageRecord(
        agent_name="test", session_id="s1", model="llama3",
        provider="ollama", input_tokens=100, output_tokens=50,
        cost_usd=0.01, latency_ms=100, pattern="react",
    )
    tracker.record(record)
    assert tracker.get_total_cost() == 0.01


def test_cost_tracker_budget():
    tracker = CostTracker()
    tracker.set_budget("test", 1.0)
    tracker.record(UsageRecord(
        agent_name="test", session_id="s1", model="m", provider="p",
        input_tokens=100, output_tokens=50, cost_usd=0.5,
        latency_ms=100, pattern="react",
    ))
    budget = tracker.check_budget("test")
    assert budget["spent"] == 0.5
    assert budget["remaining"] == 0.5
    assert not budget["exceeded"]


def test_cost_tracker_exceeded():
    tracker = CostTracker()
    tracker.set_budget("test", 0.01)
    tracker.record(UsageRecord(
        agent_name="test", session_id="s1", model="m", provider="p",
        input_tokens=100, output_tokens=50, cost_usd=0.02,
        latency_ms=100, pattern="react",
    ))
    assert tracker.check_budget("test")["exceeded"]


def test_cost_tracker_summary():
    tracker = CostTracker()
    tracker.record(UsageRecord(agent_name="a", session_id="s1", model="m1",
        provider="p1", input_tokens=100, output_tokens=50, cost_usd=0.01,
        latency_ms=100, pattern="react"))
    tracker.record(UsageRecord(agent_name="a", session_id="s2", model="m2",
        provider="p2", input_tokens=200, output_tokens=100, cost_usd=0.02,
        latency_ms=200, pattern="react"))
    summary = tracker.get_usage_summary("a")
    assert summary["total_cost"] == 0.03
    assert summary["num_calls"] == 2
    assert "p1" in summary["by_provider"]
    assert "m2" in summary["by_model"]


def test_cost_tracker_filter_by_session():
    tracker = CostTracker()
    tracker.record(UsageRecord(agent_name="a", session_id="s1", model="m",
        provider="p", input_tokens=100, output_tokens=50, cost_usd=0.01,
        latency_ms=100, pattern="react"))
    tracker.record(UsageRecord(agent_name="a", session_id="s2", model="m",
        provider="p", input_tokens=200, output_tokens=100, cost_usd=0.02,
        latency_ms=200, pattern="react"))
    assert tracker.get_total_cost(session_id="s1") == 0.01
