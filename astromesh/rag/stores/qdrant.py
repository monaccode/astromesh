from __future__ import annotations

from astromesh.rag.stores.base import VectorStore


class QdrantStore(VectorStore):
    """Vector store backed by Qdrant."""

    def __init__(
        self,
        collection_name: str = "astromesh",
        url: str = "http://localhost:6333",
        api_key: str | None = None,
        dimensions: int = 384,
    ):
        self.collection_name = collection_name
        self.url = url
        self.api_key = api_key
        self.dimensions = dimensions
        self._client = None

    def _get_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._client = QdrantClient(url=self.url, api_key=self.api_key)

            # Ensure collection exists
            collections = self._client.get_collections().collections
            if not any(c.name == self.collection_name for c in collections):
                self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=self.dimensions, distance=Distance.COSINE),
                )
        return self._client

    async def upsert(self, doc_id: str, embedding: list[float], content: str, metadata: dict):
        from qdrant_client.models import PointStruct

        client = self._get_client()
        point = PointStruct(
            id=doc_id,
            vector=embedding,
            payload={"content": content, **metadata},
        )
        client.upsert(collection_name=self.collection_name, points=[point])

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[dict]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = self._get_client()
        query_filter = None
        if filters:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()
            ]
            query_filter = Filter(must=conditions)

        results = client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=top_k,
            query_filter=query_filter,
        )

        return [
            {
                "doc_id": str(hit.id),
                "content": hit.payload.get("content", ""),
                "metadata": {k: v for k, v in hit.payload.items() if k != "content"},
                "score": hit.score,
            }
            for hit in results
        ]

    async def delete(self, doc_id: str):
        from qdrant_client.models import PointIdsList

        client = self._get_client()
        client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=[doc_id]),
        )
