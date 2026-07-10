from pathlib import Path

from astromesh.rag.loader import RAGPipelineLoader, RAGPipelineSpec


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


VALID = """
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


def test_load_file_parses_spec(tmp_path):
    p = _write(tmp_path, "pk.rag.yaml", VALID)
    spec = RAGPipelineLoader(str(tmp_path)).load_file(p)
    assert isinstance(spec, RAGPipelineSpec)
    assert spec.name == "product-knowledge"
    assert spec.chunking["strategy"] == "recursive"
    assert spec.retrieval["top_k"] == 5


def test_load_file_rejects_wrong_kind(tmp_path):
    p = _write(tmp_path, "bad.rag.yaml", "kind: Workflow\nmetadata: {name: x}\n")
    import pytest
    with pytest.raises(ValueError):
        RAGPipelineLoader(str(tmp_path)).load_file(p)


def test_load_all_indexes_by_name_and_skips_invalid(tmp_path):
    _write(tmp_path, "ok.rag.yaml", VALID)
    _write(tmp_path, "broken.rag.yaml", "kind: RAGPipeline\nmetadata: {}\n")  # no name
    reg = RAGPipelineLoader(str(tmp_path)).load_all()
    assert set(reg.keys()) == {"product-knowledge"}


def test_load_all_missing_dir_returns_empty(tmp_path):
    reg = RAGPipelineLoader(str(tmp_path / "nope")).load_all()
    assert reg == {}
