from __future__ import annotations

from astromech.rag.stores.base import VectorStore


class ChromaStore(VectorStore):
    """Vector store backed by ChromaDB."""

    def __init__(
        self,
        collection_name: str = "astromech",
        host: str | None = None,
        port: int = 8000,
        persist_directory: str | None = None,
    ):
        self.collection_name = collection_name
        self.host = host
        self.port = port
        self.persist_directory = persist_directory
        self._client = None
        self._collection = None

    def _get_collection(self):
        if self._collection is None:
            import chromadb

            if self.host:
                self._client = chromadb.HttpClient(host=self.host, port=self.port)
            elif self.persist_directory:
                self._client = chromadb.PersistentClient(path=self.persist_directory)
            else:
                self._client = chromadb.Client()

            self._collection = self._client.get_or_create_collection(
                name=self.collection_name
            )
        return self._collection

    async def upsert(
        self, doc_id: str, embedding: list[float], content: str, metadata: dict
    ):
        collection = self._get_collection()
        # Chroma requires metadata values to be str, int, float, or bool
        clean_meta = {
            k: v for k, v in metadata.items() if isinstance(v, (str, int, float, bool))
        }
        collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[clean_meta],
        )

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[dict]:
        collection = self._get_collection()
        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
        }
        if filters:
            kwargs["where"] = filters

        results = collection.query(**kwargs)

        docs: list[dict] = []
        if results and results["ids"]:
            for i, doc_id in enumerate(results["ids"][0]):
                docs.append({
                    "doc_id": doc_id,
                    "content": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "score": 1 - results["distances"][0][i] if results["distances"] else 0.0,
                })
        return docs

    async def delete(self, doc_id: str):
        collection = self._get_collection()
        collection.delete(ids=[doc_id])
