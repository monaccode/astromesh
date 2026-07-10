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
        if raw.get("kind") != "RAGPipeline":
            raise ValueError(f"Expected kind: RAGPipeline, got: {raw.get('kind')}")
        metadata = raw.get("metadata", {})
        spec = raw.get("spec", {})
        if not metadata.get("name"):
            raise ValueError("RAGPipeline missing metadata.name")
        return RAGPipelineSpec(
            name=metadata["name"],
            chunking=spec.get("chunking", {}),
            embeddings=spec.get("embeddings", {}),
            vector_store=spec.get("vector_store", {}),
            reranking=spec.get("reranking", {}),
            retrieval=spec.get("retrieval", {}),
        )
