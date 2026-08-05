from unittest.mock import AsyncMock, MagicMock

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from astromesh.api.main import app
from astromesh.api.routes import agents as agents_route


@pytest.fixture(autouse=True)
def _skip_runtime_lifespan(monkeypatch):
    monkeypatch.setenv("ASTROMESH_SKIP_RUNTIME", "1")


SAMPLE_CONFIG = {
    "apiVersion": "astromesh/v1",
    "kind": "Agent",
    "metadata": {"name": "test-agent", "version": "1.0.0", "namespace": "test"},
    "spec": {
        "identity": {"display_name": "Test", "description": "Test agent"},
        "model": {
            "primary": {
                "provider": "ollama",
                "model": "llama3.1:8b",
                "endpoint": "http://localhost:11434",
            },
            "routing": {"strategy": "cost_optimized"},
        },
        "prompts": {"system": "Test prompt."},
        "orchestration": {"pattern": "react", "max_iterations": 5},
    },
}


@pytest.fixture
def mock_runtime():
    runtime = MagicMock()
    runtime.update_agent = AsyncMock()
    runtime.deploy_agent = AsyncMock()
    runtime.pause_agent = MagicMock()
    runtime.list_agents.return_value = [
        {"name": "test-agent", "version": "1.0.0", "namespace": "test", "status": "draft"}
    ]
    agents_route.set_runtime(runtime)
    yield runtime
    agents_route.set_runtime(None)


async def test_put_agent(mock_runtime):
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        resp = await client.put("/v1/agents/test-agent", json=SAMPLE_CONFIG)
    assert resp.status_code == 200
    assert resp.json()["status"] == "updated"
    mock_runtime.update_agent.assert_awaited_once_with("test-agent", SAMPLE_CONFIG)


async def test_deploy_agent(mock_runtime):
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        resp = await client.post("/v1/agents/test-agent/deploy")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deployed"
    mock_runtime.deploy_agent.assert_awaited_once_with("test-agent")


async def test_pause_agent(mock_runtime):
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        resp = await client.post("/v1/agents/test-agent/pause")
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"
    mock_runtime.pause_agent.assert_called_once_with("test-agent")


async def test_deploy_nonexistent_returns_404(mock_runtime):
    mock_runtime.deploy_agent.side_effect = ValueError("Agent 'nope' not found")
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        resp = await client.post("/v1/agents/nope/deploy")
    assert resp.status_code == 404


async def test_deploy_with_a_program_that_does_not_compile_returns_400(mock_runtime):
    """`GlyphCompileError` no hereda de ValueError, así que la ruta —que sólo
    atrapaba ValueError— devolvía un 500 crudo. Es config inválida del cliente,
    y el mensaje del compilador trae la línea."""
    from astromesh_glyph import GlyphCompileError

    mock_runtime.deploy_agent.side_effect = GlyphCompileError("la capacidad `x` no existe", line=3)
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        resp = await client.post("/v1/agents/test-agent/deploy")
    assert resp.status_code == 400
    detalle = resp.json()["detail"]
    assert "no existe" in detalle
    assert "línea 3" in detalle


async def test_deploy_with_a_program_syntax_error_returns_400(mock_runtime):
    from astromesh_glyph import GlyphSyntaxError

    mock_runtime.deploy_agent.side_effect = GlyphSyntaxError("token inesperado", line=2, column=5)
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        resp = await client.post("/v1/agents/test-agent/deploy")
    assert resp.status_code == 400
    assert "línea 2" in resp.json()["detail"]


async def test_deploy_with_an_invalid_agent_config_returns_400_not_404(mock_runtime):
    """Un `spec.program` declarado con otro pattern es config mal escrita, no un
    agente inexistente: mandar al operador a buscar un 404 lo manda al lugar
    equivocado."""
    from astromesh.errors import AgentConfigError

    mock_runtime.deploy_agent.side_effect = AgentConfigError(
        "el agente declara `program` pero su pattern es 'react'"
    )
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        resp = await client.post("/v1/agents/test-agent/deploy")
    assert resp.status_code == 400
    assert "program" in resp.json()["detail"]


async def test_put_agent_no_runtime():
    agents_route.set_runtime(None)
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        resp = await client.put("/v1/agents/test-agent", json=SAMPLE_CONFIG)
    assert resp.status_code == 503
