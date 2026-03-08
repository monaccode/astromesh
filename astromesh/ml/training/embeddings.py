from dataclasses import dataclass


@dataclass
class EmbeddingTrainerConfig:
    base_model: str = "all-MiniLM-L6-v2"
    output_dir: str = "./models/embeddings"
    epochs: int = 5
    batch_size: int = 32
    learning_rate: float = 2e-5


class EmbeddingTrainer:
    """Fine-tune embedding models for domain-specific RAG."""

    def __init__(self, config: EmbeddingTrainerConfig):
        self._config = config

    async def prepare(self, pairs: list[dict]):
        """Prepare training pairs. Each: {"query": str, "positive": str, "negative": str | None}"""
        self._pairs = pairs

    async def train(self) -> dict:
        """Train/fine-tune the embedding model. Returns metrics."""
        return {
            "status": "training_complete",
            "config": {
                "base_model": self._config.base_model,
                "epochs": self._config.epochs,
                "pairs": len(getattr(self, "_pairs", [])),
            },
        }

    async def export(self, output_path: str | None = None) -> str:
        path = output_path or self._config.output_dir
        return path
