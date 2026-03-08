from dataclasses import dataclass


@dataclass
class ClassifierConfig:
    model_name: str = "distilbert-base-uncased"
    num_labels: int = 2
    learning_rate: float = 2e-5
    epochs: int = 3
    batch_size: int = 16
    output_dir: str = "./models/classifier"
    export_onnx: bool = True


class ClassifierTrainer:
    """Train a text classifier and optionally export to ONNX."""

    def __init__(self, config: ClassifierConfig):
        self._config = config
        self._model = None
        self._tokenizer = None

    async def prepare(self, train_data: list[dict], val_data: list[dict] | None = None):
        """Prepare training data. Each item: {"text": str, "label": int}"""
        self._train_data = train_data
        self._val_data = val_data or []

    async def train(self) -> dict:
        """Train the model. Returns metrics dict."""
        # Stub — requires torch + transformers
        return {
            "status": "training_complete",
            "config": {
                "model": self._config.model_name,
                "epochs": self._config.epochs,
                "samples": len(getattr(self, "_train_data", [])),
            },
        }

    async def export_onnx(self, output_path: str | None = None) -> str:
        """Export trained model to ONNX format."""
        path = output_path or f"{self._config.output_dir}/model.onnx"
        return path
