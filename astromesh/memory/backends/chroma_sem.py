import uuid

import chromadb

from astromesh.core.memory import SemanticBackend, SemanticMemory


class ChromaSemanticBackend(SemanticBackend):
    def __init__(self, client: chromadb.ClientAPI | None = None, path: str | None = None):
        if client is not None:
            self._client = client
        elif path:
            self._client = chromadb.PersistentClient(path=path)
        else:
            self._client = chromadb.Client()

    def _get_collection(self, agent_id: str):
        return self._client.get_or_create_collection(
            name=f"agent_{agent_id}",
            metadata={"hnsw:space": "cosine"},
        )

    async def store(self, agent_id, content, embedding, metadata):
        collection = self._get_collection(agent_id)
        memory_id = str(uuid.uuid4())
        collection.add(
            ids=[memory_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata] if metadata else None,
        )
        return memory_id

    async def search(self, agent_id, query_embedding, top_k=10, threshold=0.7):
        collection = self._get_collection(agent_id)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        memories = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                # ChromaDB returns cosine distance; similarity = 1 - distance
                distance = results["distances"][0][i] if results["distances"] else 0.0
                similarity = 1.0 - distance
                if similarity >= threshold:
                    memories.append(SemanticMemory(
                        content=results["documents"][0][i],
                        embedding=[],
                        metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                        similarity=similarity,
                        source=doc_id,
                    ))
        return memories

    async def delete(self, agent_id, memory_id):
        collection = self._get_collection(agent_id)
        collection.delete(ids=[memory_id])
