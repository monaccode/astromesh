import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from astromesh.api.main import app
from astromesh.observability.collector import InternalCollector
from astromesh.observability.tracing import TracingContext
from astromesh.api.routes.traces import set_collector


@pytest.fixture
async def collector():
    c = InternalCollector()
    set_collector(c)
    ctx = TracingContext(agent_name="test-agent", session_id="s1")
    span = ctx.start_span("agent.run")
    span.set_attribute("tokens", 100)
    span.finish()
    await c.emit_trace(ctx)
    return c, ctx.trace_id


class TestTracesAPI:
    async def test_list_traces(self, collector):
        c, trace_id = collector
        async with LifespanManager(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/v1/traces/", params={"agent": "test-agent"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["traces"]) == 1
        assert data["traces"][0]["trace_id"] == trace_id

    async def test_get_trace(self, collector):
        c, trace_id = collector
        async with LifespanManager(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(f"/v1/traces/{trace_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_id"] == trace_id

    async def test_get_trace_not_found(self, collector):
        async with LifespanManager(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/v1/traces/nonexistent")
        assert resp.status_code == 404
