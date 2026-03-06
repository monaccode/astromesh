from abc import ABC, abstractmethod


class VectorStore(ABC):
    @abstractmethod
    async def upsert(
        self, doc_id: str, embedding: list[float], content: str, metadata: dict
    ): ...

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[dict]: ...

    @abstractmethod
    async def delete(self, doc_id: str): ...
