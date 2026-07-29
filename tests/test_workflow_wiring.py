"""El WorkflowEngine debe quedar instanciado y cableado por el lifespan."""

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def workflows_config(tmp_path):
    """Un config_dir con un workflow mínimo en disco."""
    (tmp_path / "agents").mkdir()
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    (wf_dir / "ping.workflow.yaml").write_text(
        """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: ping
spec:
  description: "workflow de prueba"
  steps:
    - name: uno
      tool: noop
""",
        encoding="utf-8",
    )
    return tmp_path


async def _listar_workflows(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/v1/workflows/")


async def test_lifespan_wires_workflow_engine(workflows_config, monkeypatch):
    monkeypatch.setenv("ASTROMESH_CONFIG_DIR", str(workflows_config))
    monkeypatch.delenv("ASTROMESH_SKIP_RUNTIME", raising=False)

    from astromesh.api.main import app
    from astromesh.api.routes import agents as agents_route

    monkeypatch.setattr(agents_route, "_runtime", None)

    async with LifespanManager(app):
        resp = await _listar_workflows(app)

    assert resp.status_code == 200
    assert "ping" in resp.json()["workflows"], (
        "el lifespan no cableó el WorkflowEngine: /v1/workflows/ vino vacío"
    )


async def test_engine_survives_missing_workflows_dir(tmp_path, monkeypatch):
    """Un config_dir sin carpeta workflows/ no debe romper el arranque."""
    (tmp_path / "agents").mkdir()
    monkeypatch.setenv("ASTROMESH_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("ASTROMESH_SKIP_RUNTIME", raising=False)

    from astromesh.api.main import app
    from astromesh.api.routes import agents as agents_route

    monkeypatch.setattr(agents_route, "_runtime", None)

    async with LifespanManager(app):
        resp = await _listar_workflows(app)

    assert resp.status_code == 200
    assert resp.json()["workflows"] == []
