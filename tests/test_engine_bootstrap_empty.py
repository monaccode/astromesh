"""Un runtime sin agentes en disco se administra por API: no debe perder capacidades."""

from astromesh.runtime.engine import AgentRuntime

RAG_YAML = """
apiVersion: astromesh/v1
kind: RAGPipeline
metadata:
  name: product-knowledge
spec:
  chunking: {strategy: recursive, chunk_size: 512}
  embeddings: {provider: ollama, model: nomic-embed-text}
  vector_store: {backend: pgvector, collection: docs}
  reranking: {enabled: false}
  retrieval: {top_k: 5}
"""


async def test_rag_specs_load_when_agents_dir_is_absent(tmp_path):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    (rag_dir / "pk.rag.yaml").write_text(RAG_YAML)
    # Sin directorio 'agents': es el modo que usa un runtime administrado por API.

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    assert "product-knowledge" in runtime._rag_specs
    assert runtime.list_agents() == []


async def test_rag_specs_load_when_agents_dir_is_empty(tmp_path):
    (tmp_path / "agents").mkdir()
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    (rag_dir / "pk.rag.yaml").write_text(RAG_YAML)

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    assert "product-knowledge" in runtime._rag_specs
    assert runtime.list_agents() == []
