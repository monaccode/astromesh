import uuid

import numpy as np
import faiss

from astromech.core.memory import SemanticBackend, SemanticMemory


class FAISSSemanticBackend(SemanticBackend):
    def __init__(self, dimension: int = 1536):
        self._dimension = dimension
        self._indices: dict[str, faiss.IndexFlatIP] = {}
        self._data: dict[str, list[dict]] = {}

    def _ensure_index(self, agent_id: str):
        if agent_id not in self._indices:
            self._indices[agent_id] = faiss.IndexFlatIP(self._dimension)
            self._data[agent_id] = []

    async def store(self, agent_id, content, embedding, metadata):
        self._ensure_index(agent_id)
        memory_id = str(uuid.uuid4())
        vec = np.array([embedding], dtype=np.float32)
        # Normalize for cosine similarity with IndexFlatIP
        faiss.normalize_L2(vec)
        self._indices[agent_id].add(vec)
        self._data[agent_id].append({
            "id": memory_id,
            "content": content,
            "embedding": embedding,
            "metadata": metadata,
        })
        return memory_id

    async def search(self, agent_id, query_embedding, top_k=10, threshold=0.7):
        self._ensure_index(agent_id)
        if self._indices[agent_id].ntotal == 0:
            return []

        query_vec = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(query_vec)
        k = min(top_k, self._indices[agent_id].ntotal)
        scores, indices = self._indices[agent_id].search(query_vec, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or float(score) < threshold:
                continue
            entry = self._data[agent_id][idx]
            results.append(SemanticMemory(
                content=entry["content"],
                embedding=entry["embedding"],
                metadata=entry["metadata"],
                similarity=float(score),
                source=entry["id"],
            ))
        return results

    async def delete(self, agent_id, memory_id):
        if agent_id not in self._data:
            return
        # Find and remove the entry, then rebuild the index
        new_data = [e for e in self._data[agent_id] if e["id"] != memory_id]
        if len(new_data) == len(self._data[agent_id]):
            return  # Not found

        self._data[agent_id] = new_data
        self._indices[agent_id] = faiss.IndexFlatIP(self._dimension)
        if new_data:
            vecs = np.array([e["embedding"] for e in new_data], dtype=np.float32)
            faiss.normalize_L2(vecs)
            self._indices[agent_id].add(vecs)
