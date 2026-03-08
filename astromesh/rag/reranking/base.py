from abc import ABC, abstractmethod


class Reranker(ABC):
    @abstractmethod
    async def rerank(
        self, query: str, documents: list[dict], top_k: int = 5
    ) -> list[dict]: ...
