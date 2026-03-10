import json
from io import StringIO

from astromesh.observability.tracing import TracingContext, Span, SpanStatus


class TestSpan:
    def test_span_creation(self):
        span = Span(name="test.span", trace_id="trace-1")
        assert span.name == "test.span"
        assert span.trace_id == "trace-1"
        assert span.parent_span_id is None
        assert span.status == SpanStatus.UNSET

    def test_span_finish(self):
        span = Span(name="test.span", trace_id="trace-1")
        span.finish(status=SpanStatus.OK)
        assert span.status == SpanStatus.OK
        assert span.duration_ms >= 0

    def test_span_set_attribute(self):
        span = Span(name="test.span", trace_id="trace-1")
        span.set_attribute("key", "value")
        assert span.attributes["key"] == "value"

    def test_span_add_event(self):
        span = Span(name="test.span", trace_id="trace-1")
        span.add_event("something.happened", {"detail": "info"})
        assert len(span.events) == 1
        assert span.events[0]["name"] == "something.happened"

    def test_span_to_dict(self):
        span = Span(name="test.span", trace_id="trace-1")
        span.set_attribute("key", "val")
        span.finish(status=SpanStatus.OK)
        d = span.to_dict()
        assert d["name"] == "test.span"
        assert d["trace_id"] == "trace-1"
        assert d["status"] == "ok"
        assert "duration_ms" in d


class TestTracingContext:
    def test_create_trace(self):
        ctx = TracingContext(agent_name="test-agent", session_id="sess-1")
        assert ctx.trace_id is not None
        assert ctx.agent_name == "test-agent"

    def test_start_and_finish_span(self):
        ctx = TracingContext(agent_name="test-agent", session_id="sess-1")
        span = ctx.start_span("test.operation")
        assert span.trace_id == ctx.trace_id
        span.finish(status=SpanStatus.OK)
        assert len(ctx.spans) == 1

    def test_nested_spans(self):
        ctx = TracingContext(agent_name="test-agent", session_id="sess-1")
        parent = ctx.start_span("parent")
        child = ctx.start_span("child")
        assert child.parent_span_id == parent.span_id
        child.finish(status=SpanStatus.OK)
        parent.finish(status=SpanStatus.OK)
        assert len(ctx.spans) == 2

    def test_to_dict(self):
        ctx = TracingContext(agent_name="test-agent", session_id="sess-1")
        span = ctx.start_span("op")
        span.finish(status=SpanStatus.OK)
        d = ctx.to_dict()
        assert d["trace_id"] == ctx.trace_id
        assert d["agent"] == "test-agent"
        assert len(d["spans"]) == 1

    def test_sample_rate_zero_disables_spans(self):
        ctx = TracingContext(agent_name="test-agent", session_id="sess-1", sample_rate=0.0)
        span = ctx.start_span("op")
        span.finish(status=SpanStatus.OK)
        assert ctx.is_sampled is False


class TestStructuredLogger:
    def test_log_event(self):
        from astromesh.observability.logging import StructuredLogger

        output = StringIO()
        logger = StructuredLogger(stream=output)
        logger.info(
            "tool.executed",
            agent="test-agent",
            trace_id="trace-1",
            tool="web_search",
            duration_ms=150,
            status="success",
        )
        line = output.getvalue().strip()
        data = json.loads(line)
        assert data["level"] == "info"
        assert data["event"] == "tool.executed"
        assert data["agent"] == "test-agent"
        assert data["tool"] == "web_search"
        assert "timestamp" in data

    def test_log_error(self):
        from astromesh.observability.logging import StructuredLogger

        output = StringIO()
        logger = StructuredLogger(stream=output)
        logger.error("tool.failed", tool="sql_query", error="Connection refused")
        line = output.getvalue().strip()
        data = json.loads(line)
        assert data["level"] == "error"
        assert data["error"] == "Connection refused"


class TestStdoutCollector:
    async def test_emit_trace(self):
        from astromesh.observability.collector import StdoutCollector

        output = StringIO()
        collector = StdoutCollector(stream=output)
        ctx = TracingContext(agent_name="test", session_id="s1")
        span = ctx.start_span("op")
        span.finish()
        await collector.emit_trace(ctx)
        line = output.getvalue().strip()
        data = json.loads(line)
        assert data["trace_id"] == ctx.trace_id


class TestInternalCollector:
    async def test_store_and_query_trace(self):
        from astromesh.observability.collector import InternalCollector

        collector = InternalCollector()
        ctx = TracingContext(agent_name="test-agent", session_id="s1")
        span = ctx.start_span("op")
        span.finish()
        await collector.emit_trace(ctx)
        traces = await collector.query_traces(agent="test-agent", limit=10)
        assert len(traces) == 1
        assert traces[0]["trace_id"] == ctx.trace_id

    async def test_query_by_trace_id(self):
        from astromesh.observability.collector import InternalCollector

        collector = InternalCollector()
        ctx = TracingContext(agent_name="test", session_id="s1")
        span = ctx.start_span("op")
        span.finish()
        await collector.emit_trace(ctx)
        trace = await collector.get_trace(ctx.trace_id)
        assert trace is not None
        assert trace["agent"] == "test"

    async def test_query_empty(self):
        from astromesh.observability.collector import InternalCollector

        collector = InternalCollector()
        traces = await collector.query_traces(agent="none", limit=10)
        assert traces == []
