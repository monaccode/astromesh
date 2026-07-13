from astromesh.workflow.models import WorkflowSpec
from astromesh.workflow.store import InMemoryRunStore


def _engine(store=None):
    from astromesh.workflow import WorkflowEngine

    return WorkflowEngine(
        workflows_dir="", runtime=None, tool_registry=None, store=store or InMemoryRunStore()
    )


def test_register_workflow_adds_to_registry():
    eng = _engine()
    spec = WorkflowSpec(name="wf-dyn", steps=[])  # los demás campos tienen defaults
    assert "wf-dyn" not in eng.list_workflows()
    eng.register_workflow(spec)
    assert "wf-dyn" in eng.list_workflows()
    assert eng.get_workflow("wf-dyn") is spec


def test_register_workflow_is_upsert():
    eng = _engine()
    s1 = WorkflowSpec(name="wf", version="1.0.0", steps=[])
    s2 = WorkflowSpec(name="wf", version="2.0.0", steps=[])
    eng.register_workflow(s1)
    eng.register_workflow(s2)
    assert eng.get_workflow("wf").version == "2.0.0"


def test_register_rag_pipeline_adds_to_runtime_store():
    from astromesh.runtime.engine import AgentRuntime

    rt = AgentRuntime(config_dir="/nonexistent")
    raw = {
        "apiVersion": "astromesh/v1",
        "kind": "RAGPipeline",
        "metadata": {"name": "kb-dyn", "version": "1.0.0"},
        "spec": {
            "description": "d",
            "chunking": {"strategy": "recursive", "chunk_size": 800},
            "embeddings": {"provider": "ollama", "model": "nomic-embed-text"},
            "vector_store": {"backend": "pgvector"},
            "retrieval": {"top_k": 5},
        },
    }
    name = rt.register_rag_pipeline(raw)
    assert name == "kb-dyn"
    assert "kb-dyn" in rt._rag_specs
    assert rt._rag_specs["kb-dyn"].name == "kb-dyn"
