"""Fase 4.3b: engine metrics derived from the TracingContext span tree."""


class _FakeInstr:
    def __init__(self, name, sink):
        self.name = name
        self._sink = sink

    def add(self, value, attrs=None):
        self._sink.append((self.name, "add", value, attrs or {}))

    def record(self, value, attrs=None):
        self._sink.append((self.name, "record", value, attrs or {}))


def _mgr_with_fakes(sink):
    from astromesh.observability import metrics_export as mx
    m = mx.MetricsManager(enabled=False)  # disabled -> setup() creates no real instruments
    m.setup()
    # inject capturing fakes (matches the private-attr style of test_agent_egress_metric.py)
    m._runs = _FakeInstr("runs", sink)
    m._latency = _FakeInstr("latency", sink)
    m._llm_calls = _FakeInstr("llm_calls", sink)
    m._llm_latency = _FakeInstr("llm_latency", sink)
    m._tokens = _FakeInstr("tokens", sink)
    m._cost = _FakeInstr("cost", sink)
    m._tools = _FakeInstr("tools", sink)
    return m


def _build_ctx():
    from astromesh.observability.tracing import TracingContext, SpanStatus
    ctx = TracingContext(agent_name="rec-agent", session_id="s1")
    root = ctx.start_span("agent.run", {"agent": "rec-agent", "session": "s1"})
    llm = ctx.start_span("llm.complete")
    llm.set_attribute("model", "m"); llm.set_attribute("provider", "p")
    llm.set_attribute("latency_ms", 1500.0); llm.set_attribute("cost", 0.02)
    llm.set_attribute("input_tokens", 10); llm.set_attribute("output_tokens", 5)
    ctx.finish_span(llm, status=SpanStatus.OK)
    tool = ctx.start_span("tool.call", {"tool": "search"})
    ctx.finish_span(tool, status=SpanStatus.OK)
    ctx.finish_span(root, status=SpanStatus.OK)
    return ctx


def test_record_run_derives_full_metric_set():
    sink = []
    m = _mgr_with_fakes(sink)
    m.record_run(_build_ctx())

    # agent.run -> runs counter + latency histogram
    assert ("runs", "add", 1, {"agent": "rec-agent", "status": "ok"}) in sink
    assert any(n == "latency" and op == "record" and v > 0 and a == {"agent": "rec-agent"}
               for (n, op, v, a) in sink)
    # llm.complete -> llm.calls + llm.latency + tokens(in/out) + cost
    assert ("llm_calls", "add", 1, {"provider": "p", "model": "m", "status": "ok"}) in sink
    assert any(n == "llm_latency" and abs(v - 1.5) < 1e-6 for (n, op, v, a) in sink)
    assert ("tokens", "add", 10, {"agent": "rec-agent", "direction": "input"}) in sink
    assert ("tokens", "add", 5, {"agent": "rec-agent", "direction": "output"}) in sink
    assert ("cost", "add", 0.02, {"agent": "rec-agent", "model": "m"}) in sink
    # tool.call -> tool.executions
    assert ("tools", "add", 1, {"tool": "search", "status": "ok"}) in sink


def test_record_run_is_best_effort_when_disabled():
    from astromesh.observability import metrics_export as mx
    m = mx.MetricsManager(enabled=False)
    m.setup()  # instruments stay None
    # must not raise even with no instruments and an empty/None ctx
    m.record_run(_build_ctx())

    class _Empty:
        spans = []
        agent_name = "x"
    m.record_run(_Empty())


async def test_engine_calls_record_run(tmp_path):
    from astromesh.observability import metrics_export as mx
    from astromesh.runtime.engine import AgentRuntime

    seen = {"record_run": 0, "agent_run_span": False}

    class CapMgr:
        def record(self, agent, model, n):
            pass

        def record_run(self, ctx):
            seen["record_run"] += 1
            if any(getattr(s, "name", "") == "agent.run" for s in getattr(ctx, "spans", [])):
                seen["agent_run_span"] = True

        def flush(self, timeout_millis=5000):
            pass

    mx.set_manager(CapMgr())

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
        model = "m"; provider = "p"; content = "hi"; tool_calls = None
        usage = {"input_tokens": 3, "output_tokens": 2}; latency_ms = 1.0; cost = 0.0

    async def fake_route(messages, tools=None, **kw):
        return Resp()

    agent._routers["default"].route = fake_route

    try:
        await rt.run("rec-agent", "hello there", "s1")
    except Exception:
        pass

    assert seen["record_run"] >= 1
    assert seen["agent_run_span"] is True
