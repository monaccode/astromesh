from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ModelFormat(str, Enum):
    ONNX = "onnx"
    PYTORCH = "pytorch"
    SAFETENSORS = "safetensors"


class ModelStatus(str, Enum):
    REGISTERED = "registered"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"


@dataclass
class ModelInfo:
    name: str
    version: str
    format: ModelFormat
    path: str
    task: str  # e.g., "classification", "embedding", "generation"
    metadata: dict = field(default_factory=dict)
    status: ModelStatus = ModelStatus.REGISTERED
    instance: Any = None


class ModelRegistry:
    """Local ML model registry — register, load, serve, and manage models."""

    def __init__(self, models_dir: str = "./models"):
        self._models: dict[str, ModelInfo] = {}
        self._models_dir = Path(models_dir)

    def register(self, name: str, version: str, format: ModelFormat,
                 path: str, task: str, metadata: dict | None = None) -> ModelInfo:
        key = f"{name}:{version}"
        info = ModelInfo(name=name, version=version, format=format,
                        path=path, task=task, metadata=metadata or {})
        self._models[key] = info
        return info

    def get(self, name: str, version: str = "latest") -> ModelInfo | None:
        if version == "latest":
            candidates = [v for k, v in self._models.items() if k.startswith(f"{name}:")]
            return candidates[-1] if candidates else None
        return self._models.get(f"{name}:{version}")

    def list_models(self, task: str | None = None) -> list[ModelInfo]:
        models = list(self._models.values())
        if task:
            models = [m for m in models if m.task == task]
        return models

    async def load(self, name: str, version: str = "latest") -> ModelInfo:
        info = self.get(name, version)
        if not info:
            raise ValueError(f"Model '{name}:{version}' not found")

        info.status = ModelStatus.LOADING
        try:
            if info.format == ModelFormat.ONNX:
                info.instance = await self._load_onnx(info)
            elif info.format == ModelFormat.PYTORCH:
                info.instance = await self._load_pytorch(info)
            info.status = ModelStatus.READY
        except Exception as e:
            info.status = ModelStatus.ERROR
            raise RuntimeError(f"Failed to load model: {e}") from e
        return info

    async def _load_onnx(self, info: ModelInfo):
        try:
            import onnxruntime as ort
            providers = ["CPUExecutionProvider"]
            if info.metadata.get("device") == "cuda":
                providers.insert(0, "CUDAExecutionProvider")
            return ort.InferenceSession(info.path, providers=providers)
        except ImportError:
            raise RuntimeError("onnxruntime not installed")

    async def _load_pytorch(self, info: ModelInfo):
        try:
            import torch
            model = torch.jit.load(info.path)
            model.eval()
            return model
        except ImportError:
            raise RuntimeError("torch not installed")

    async def predict(self, name: str, input_data: Any, version: str = "latest") -> Any:
        info = self.get(name, version)
        if not info or info.status != ModelStatus.READY:
            raise RuntimeError(f"Model '{name}:{version}' not ready")

        if info.format == ModelFormat.ONNX:
            return info.instance.run(None, input_data)
        elif info.format == ModelFormat.PYTORCH:
            import torch
            with torch.no_grad():
                return info.instance(input_data)

    def unregister(self, name: str, version: str):
        key = f"{name}:{version}"
        self._models.pop(key, None)
