from astromesh.rag.loader import RAGPipelineSpec
from astromesh.runtime.engine import AgentRuntime


def _engine_with_registry():
    eng = AgentRuntime(config_dir="./config")
    eng._rag_specs = {
        "product-knowledge": RAGPipelineSpec(
            name="product-knowledge",
            chunking={"strategy": "recursive"},
            embeddings={"provider": "ollama"},
            vector_store={"backend": "faiss", "dimensions": 8},
            reranking={"enabled": False},
            retrieval={"top_k": 4},
        )
    }
    return eng


def _agent_config(knowledge: dict | None):
    spec = {
        "model": {},
        "prompts": {"system": "hola"},
        "orchestration": {"pattern": "react"},
    }
    if knowledge is not None:
        spec["knowledge"] = knowledge
    return {"metadata": {"name": "a1"}, "spec": spec}


def test_agent_with_knowledge_gets_rag():
    eng = _engine_with_registry()
    agent = eng._build_agent(_agent_config({"pipeline": "product-knowledge", "top_k": 3}))
    assert agent._rag is not None
    assert agent._rag._top_k == 3


def test_agent_without_knowledge_has_no_rag():
    eng = _engine_with_registry()
    agent = eng._build_agent(_agent_config(None))
    assert agent._rag is None


def test_agent_with_unresolved_pipeline_degrades_to_none():
    eng = _engine_with_registry()
    agent = eng._build_agent(_agent_config({"pipeline": "does-not-exist"}))
    assert agent._rag is None
