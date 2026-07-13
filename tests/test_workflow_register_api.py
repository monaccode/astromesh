# tests/test_workflow_register_api.py
import pytest

from astromesh.api.routes import workflows as wf_route


class _FakeRuntime:
    def __init__(self):
        self.calls = []  # orden de operaciones
        self.deployed = []

    async def register_agent(self, config: dict):
        self.calls.append(("register_agent", config["metadata"]["name"]))

    async def deploy_agent(self, name: str):
        self.calls.append(("deploy_agent", name))
        self.deployed.append(name)

    def register_rag_pipeline(self, raw: dict) -> str:
        name = raw["metadata"]["name"]
        self.calls.append(("register_rag_pipeline", name))
        return name


class _FakeEngine:
    def __init__(self, runtime):
        self._runtime = runtime
        self.registered = []

    def register_workflow(self, spec):
        self.registered.append(spec.name)


def _blueprint():
    return {
        "workflow": {
            "apiVersion": "astromesh/v1",
            "kind": "Workflow",
            "metadata": {"name": "compras-wf", "version": "1.0.0"},
            "spec": {
                "trigger": "api",
                "timeout_seconds": 900,
                "steps": [
                    {"name": "Aprobar", "approval": {"approver": "role:fin", "prompt": "ok?"}}
                ],
            },
        },
        "agents": [
            {
                "apiVersion": "astromesh/v1",
                "kind": "Agent",
                "metadata": {"name": "compras-sup", "version": "1.0.0"},
                "spec": {
                    "identity": {"display_name": "Sup"},
                    "prompts": {"system": "s"},
                    "model": {"primary": {"provider": "openai", "model": "gpt-4o"}},
                    "orchestration": {"pattern": "react"},
                },
            },
        ],
        "rag_pipelines": [
            {
                "apiVersion": "astromesh/v1",
                "kind": "RAGPipeline",
                "metadata": {"name": "compras-kb", "version": "1.0.0"},
                "spec": {
                    "description": "d",
                    "chunking": {"strategy": "recursive", "chunk_size": 800},
                    "embeddings": {"provider": "ollama", "model": "nomic-embed-text"},
                    "vector_store": {"backend": "pgvector"},
                    "retrieval": {"top_k": 5},
                },
            },
        ],
    }


@pytest.fixture
def _fake(request):
    rt = _FakeRuntime()
    eng = _FakeEngine(rt)
    wf_route.set_workflow_engine(eng)
    yield eng, rt
    wf_route.set_workflow_engine(None)


async def test_register_blueprint_registers_all_in_order(client, _fake):
    eng, rt = _fake
    resp = await client.post("/v1/workflows/register", json=_blueprint())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workflow_name"] == "compras-wf"
    assert body["agents"] == ["compras-sup"]
    assert body["rag_pipelines"] == ["compras-kb"]
    assert eng.registered == ["compras-wf"]  # el workflow lo registra el engine
    # orden: RAG primero, luego agente (register+deploy)
    assert rt.calls == [
        ("register_rag_pipeline", "compras-kb"),
        ("register_agent", "compras-sup"),
        ("deploy_agent", "compras-sup"),
    ]


async def test_register_is_idempotent(client, _fake):
    eng, rt = _fake
    await client.post("/v1/workflows/register", json=_blueprint())
    resp = await client.post("/v1/workflows/register", json=_blueprint())
    assert resp.status_code == 200
    assert eng.registered == ["compras-wf", "compras-wf"]  # overwrite, sin error


async def test_register_503_when_engine_uninitialized(client):
    wf_route.set_workflow_engine(None)
    resp = await client.post("/v1/workflows/register", json=_blueprint())
    assert resp.status_code == 503


async def test_register_422_on_bad_workflow(client, _fake):
    bp = _blueprint()
    bp["workflow"]["kind"] = "NotAWorkflow"
    resp = await client.post("/v1/workflows/register", json=bp)
    assert resp.status_code == 422


async def test_register_approval_only_blueprint_then_run_real_engine(client):
    """Integration: real WorkflowEngine + real AgentRuntime (no fakes), approval-only
    blueprint (agents=[], rag_pipelines=[]) — register -> list -> run -> suspended -> approvals.
    Mirrors the `wired` fixture pattern in test_workflow_approval_api.py but builds a
    real engine via WorkflowEngine.bootstrap() instead of poking `_workflows` directly."""
    from astromesh.runtime.engine import AgentRuntime
    from astromesh.workflow import WorkflowEngine
    from astromesh.workflow.store import InMemoryRunStore

    runtime = AgentRuntime(config_dir="__no_such_config_dir__")
    eng = WorkflowEngine(
        workflows_dir="", runtime=runtime, tool_registry=None, store=InMemoryRunStore()
    )
    await eng.bootstrap()
    wf_route.set_workflow_engine(eng)
    try:
        bp = _blueprint()
        bp["agents"] = []
        bp["rag_pipelines"] = []

        resp = await client.post("/v1/workflows/register", json=bp)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "workflow_name": "compras-wf",
            "agents": [],
            "rag_pipelines": [],
        }

        assert "compras-wf" in eng.list_workflows()

        run_resp = await client.post("/v1/workflows/compras-wf/run", json={"trigger": {}})
        assert run_resp.status_code == 200, run_resp.text
        assert run_resp.json()["status"] == "suspended"

        approvals_resp = await client.get("/v1/workflows/approvals")
        assert approvals_resp.status_code == 200
        names = [a["workflow_name"] for a in approvals_resp.json()["approvals"]]
        assert "compras-wf" in names
    finally:
        wf_route.set_workflow_engine(None)
