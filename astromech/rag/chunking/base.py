from abc import ABC, abstractmethod


class ChunkingStrategy(ABC):
    @abstractmethod
    def chunk(self, document: str, metadata: dict) -> list[dict]: ...
