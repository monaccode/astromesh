from dataclasses import dataclass
from typing import Any


@dataclass
class ONNXServingConfig:
    model_path: str
    device: str = "cpu"
    num_threads: int = 4
    optimization_level: int = 1


class ONNXModelServer:
    """Serve ONNX models with optimized inference."""

    def __init__(self, config: ONNXServingConfig):
        self._config = config
        self._session = None

    async def load(self):
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = self._config.num_threads
            opts.graph_optimization_level = ort.GraphOptimizationLevel(self._config.optimization_level)
            providers = ["CPUExecutionProvider"]
            if self._config.device == "cuda":
                providers.insert(0, "CUDAExecutionProvider")
            self._session = ort.InferenceSession(self._config.model_path, opts, providers=providers)
        except ImportError:
            raise RuntimeError("onnxruntime not installed")

    async def predict(self, inputs: dict) -> Any:
        if not self._session:
            await self.load()
        return self._session.run(None, inputs)

    def get_input_names(self) -> list[str]:
        if self._session:
            return [inp.name for inp in self._session.get_inputs()]
        return []

    def get_output_names(self) -> list[str]:
        if self._session:
            return [out.name for out in self._session.get_outputs()]
        return []
