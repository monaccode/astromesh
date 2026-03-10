from dataclasses import dataclass
from typing import Any


@dataclass
class TorchServingConfig:
    model_path: str
    device: str = "cpu"
    dtype: str = "float32"


class TorchModelServer:
    """Serve PyTorch models."""

    def __init__(self, config: TorchServingConfig):
        self._config = config
        self._model = None

    async def load(self):
        try:
            import torch

            self._model = torch.jit.load(self._config.model_path)
            device = torch.device(self._config.device)
            self._model = self._model.to(device)
            self._model.eval()
        except ImportError:
            raise RuntimeError("torch not installed")

    async def predict(self, inputs: Any) -> Any:
        if not self._model:
            await self.load()
        import torch

        with torch.no_grad():
            return self._model(inputs)
