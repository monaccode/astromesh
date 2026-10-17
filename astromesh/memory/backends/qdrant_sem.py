import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from astromesh.core.memory import SemanticBackend, SemanticMemory


class QdrantSemanticBackend(SemanticBackend):
    def __init__(
        self,
        client: QdrantClient | None = None,
        url: str | None = None,
        dimension: int = 1536,
    ):
        if client is not None:
            self._client = client
        elif url:
            self._client = QdrantClient(url=url)
        else:
            self._client = QdrantClient(":memory:")
        self._dimension = dimension

    def _collection_name(self, agent_id: str) -> str:
        return f"agent_{agent_id}"

    def _ensure_collection(self, agent_id: str):
        name = self._collection_name(agent_id)
        collections = [c.name for c in self._client.get_collections().collections]
        if name not in collections:
            self._client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=self._dimension,
                    distance=Distance.COSINE,
                ),
            )

    async def store(self, agent_id, content, embedding, metadata):
        self._ensure_collection(agent_id)
        memory_id = str(uuid.uuid4())
        payload = {"content": content, "metadata": metadata}
        self._client.upsert(
            collection_name=self._collection_name(agent_id),
            points=[
                PointStruct(
                    id=memory_id,
                    vector=embedding,
                    payload=payload,
                )
            ],
        )
        return memory_id

    async def search(self, agent_id, query_embedding, top_k=10, threshold=0.7, session_id=None):
        self._ensure_collection(agent_id)
        filtro = None
        if session_id is not None:
            filtro = Filter(
                must=[FieldCondition(key="metadata.session_id", match=MatchValue(value=session_id))]
            )
        # `query_points`, no `search`: qdrant-client 1.13+ quitó `search` (el extra pide >=1.11).
        results = self._client.query_points(
            collection_name=self._collection_name(agent_id),
            query=query_embedding,
            limit=top_k,
            score_threshold=threshold,
            query_filter=filtro,
        ).points
        return [
            SemanticMemory(
                content=hit.payload.get("content", ""),
                embedding=[],
                metadata=hit.payload.get("metadata", {}),
                similarity=hit.score,
                source=str(hit.id),
            )
            for hit in results
        ]

    async def delete(self, agent_id, memory_id):
        self._client.delete(
            collection_name=self._collection_name(agent_id),
            points_selector=[memory_id],
        )
