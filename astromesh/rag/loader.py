from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class RAGPipelineSpec:
    name: str
    chunking: dict = field(default_factory=dict)
    embeddings: dict = field(default_factory=dict)
    vector_store: dict = field(default_factory=dict)
    reranking: dict = field(default_factory=dict)
    retrieval: dict = field(default_factory=dict)


_SPEC_SECTIONS = ("chunking", "embeddings", "vector_store", "reranking", "retrieval")


def spec_from_raw(raw: dict) -> RAGPipelineSpec:
    """Build a RAGPipelineSpec from a raw config dict. Validates kind + name.

    Every structural node (metadata, spec, and each spec section) is type-checked
    to be a mapping. Without this, a structurally-plausible-but-malformed body
    (e.g. ``spec.vector_store: "faiss"`` as a scalar) would pass validation, get
    stored, and then raise AttributeError inside the summary serializer — turning
    one bad document into a 500 for the entire list endpoint.
    """
    if not isinstance(raw, dict):
        raise ValueError("RAGPipeline body must be a mapping")
    if raw.get("kind") != "RAGPipeline":
        raise ValueError(f"Expected kind: RAGPipeline, got: {raw.get('kind')}")
    metadata = raw.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("RAGPipeline metadata must be a mapping")
    if not metadata.get("name"):
        raise ValueError("RAGPipeline missing metadata.name")
    spec = raw.get("spec", {})
    if not isinstance(spec, dict):
        raise ValueError("RAGPipeline spec must be a mapping")
    for section in _SPEC_SECTIONS:
        if section in spec and not isinstance(spec[section], dict):
            raise ValueError(f"RAGPipeline spec.{section} must be a mapping")
    return RAGPipelineSpec(
        name=metadata["name"],
        chunking=spec.get("chunking", {}),
        embeddings=spec.get("embeddings", {}),
        vector_store=spec.get("vector_store", {}),
        reranking=spec.get("reranking", {}),
        retrieval=spec.get("retrieval", {}),
    )


class RAGPipelineLoader:
    """Loads *.rag.yaml files into RAGPipelineSpec instances. Mirrors WorkflowLoader."""

    def __init__(self, rag_dir: str):
        self._dir = Path(rag_dir)

    def load_all(self) -> dict[str, RAGPipelineSpec]:
        if not self._dir.exists():
            return {}
        out: dict[str, RAGPipelineSpec] = {}
        for f in self._dir.glob("*.rag.yaml"):
            try:
                spec = self.load_file(f)
            except Exception:
                continue  # skip invalid files
            out[spec.name] = spec
        return out

    def load_file(self, path: Path) -> RAGPipelineSpec:
        raw = yaml.safe_load(path.read_text())
        return spec_from_raw(raw)
