# tests/test_workflow_api.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from fastapi import FastAPI
from astromesh.api.routes.workflows import router, set_workflow_engine
from astromesh.workflow.models import WorkflowRunResult, StepResult, StepStatus


def _make_app():
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    return app


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.list_workflows.return_value = ["wf-alpha", "wf-beta"]
    engine.get_workflow.return_value = MagicMock(
        name="wf-alpha",
        version="0.1.0",
        namespace="default",
        description="Test workflow",
        trigger="api",
        timeout_seconds=300,
        steps=[MagicMock(name="s1", step_type=MagicMock(value="agent"))],
    )
    engine.run = AsyncMock(
        return_value=WorkflowRunResult(
            workflow_name="wf-alpha",
            status="completed",
            steps={"s1": StepResult(name="s1", status=StepStatus.SUCCESS, output={"answer": "ok"})},
            output={"answer": "ok"},
            trace={"trace_id": "abc123", "spans": []},
            duration_ms=150.0,
        )
    )
    return engine


class TestWorkflowAPI:
    async def test_list_workflows(self, mock_engine):
        set_workflow_engine(mock_engine)
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/workflows/")
        assert resp.status_code == 200
        data = resp.json()
        assert "wf-alpha" in data["workflows"]

    async def test_get_workflow(self, mock_engine):
        set_workflow_engine(mock_engine)
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/workflows/wf-alpha")
        assert resp.status_code == 200

    async def test_get_workflow_not_found(self, mock_engine):
        mock_engine.get_workflow.return_value = None
        set_workflow_engine(mock_engine)
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/workflows/nonexistent")
        assert resp.status_code == 404

    async def test_run_workflow(self, mock_engine):
        set_workflow_engine(mock_engine)
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/v1/workflows/wf-alpha/run", json={"query": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["workflow_name"] == "wf-alpha"

    async def test_run_workflow_not_found(self, mock_engine):
        mock_engine.run = AsyncMock(side_effect=ValueError("Workflow 'ghost' not found"))
        set_workflow_engine(mock_engine)
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/v1/workflows/ghost/run", json={"query": "hi"})
        assert resp.status_code == 404

    async def test_run_workflow_no_engine(self):
        set_workflow_engine(None)
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/v1/workflows/any/run", json={"query": "hi"})
        assert resp.status_code == 503
