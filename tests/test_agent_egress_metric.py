"""Fase 4.4c: per-agent egress byte attribution exported as OTLP metrics."""


def test_metrics_manager_record_and_global():
    from astromesh.observability import metrics_export as mx
    m = mx.MetricsManager(endpoint="http://127.0.0.1:4317", enabled=False)  # disabled -> no exporter
    m.setup()
    m.record("agent-a", "model-x", 123)  # must not raise even when disabled
    m.flush()
    mx.set_manager(m)
    assert mx.get_manager() is m


async def test_engine_records_agent_egress(tmp_path):
    from astromesh.observability import metrics_export as mx
    from astromesh.runtime.engine import AgentRuntime

    recorded = []

    class FakeMgr:
        def record(self, agent, model, n):
            recorded.append((agent, model, n))

        def flush(self, timeout_millis=5000):
            pass

    mx.set_manager(FakeMgr())

    agents_dir = tmp_path / "agents"; agents_dir.mkdir()
    (agents_dir / "a.agent.yaml").write_text(
        """
apiVersion: astromesh/v1
kind: Agent
metadata: {name: rec-agent, version: "0.1.0", namespace: t}
spec:
  identity: {display_name: A, description: A}
  model: {primary: {provider: ollama, model: m, endpoint: "http://127.0.0.1:1/v1"}}
  prompts: {system: "sys"}
  orchestration: {pattern: react, max_iterations: 1}
"""
    )
    rt = AgentRuntime(config_dir=str(tmp_path)); await rt.bootstrap()
    agent = rt._agents["rec-agent"]

    class Resp:
        model = "m"
        provider = "p"
        content = "hi"
        tool_calls = None
        usage = {}
        latency_ms = 1.0
        cost = 0.0

    async def fake_route(messages, tools=None, **kw):
        return Resp()

    agent._router.route = fake_route

    try:
        await rt.run("rec-agent", "hello there", "s1")
    except Exception:
        pass

    assert any(a == "rec-agent" and n > 0 for (a, mdl, n) in recorded)
