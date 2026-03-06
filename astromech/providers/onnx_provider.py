"""ONNX Runtime provider adapter for the Astromech Agent Runtime."""

from __future__ import annotations

import time
from typing import Any, AsyncIterator

from .base import CompletionChunk, CompletionResponse


class ONNXProvider:
    """Provider adapter that runs inference locally via ONNX Runtime.

    This provider is *not* HTTP-based.  It loads an ONNX model from disk and
    runs inference in-process.  The model is lazily loaded on first use.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.model_path: str = config.get("model_path", "")
        self.model_name: str = config.get("model", "onnx-local")
        self._session: Any = None

    def _load_model(self) -> Any:
        """Lazily load the ONNX model into an InferenceSession."""
        if self._session is None:
            try:
                import onnxruntime as ort  # type: ignore[import-untyped]

                self._session = ort.InferenceSession(self.model_path)
            except ImportError as exc:
                raise ImportError(
                    "onnxruntime is required for ONNXProvider. "
                    "Install it with: pip install onnxruntime"
                ) from exc
        return self._session

    async def complete(self, messages: list[dict], **kwargs: Any) -> CompletionResponse:
        session = self._load_model()

        # Build a simple text prompt from messages
        prompt = "\n".join(m.get("content", "") for m in messages)

        start = time.perf_counter()
        # Run inference — the exact I/O depends on the model.
        input_name = session.get_inputs()[0].name
        import numpy as np  # type: ignore[import-untyped]

        input_ids = np.array([[ord(c) for c in prompt[:512]]], dtype=np.int64)
        outputs = session.run(None, {input_name: input_ids})
        latency_ms = (time.perf_counter() - start) * 1000

        content = str(outputs[0]) if outputs else ""

        return CompletionResponse(
            content=content,
            model=self.model_name,
            provider="onnx",
            usage={"input_tokens": len(prompt.split()), "output_tokens": len(content.split())},
            latency_ms=latency_ms,
            cost=0.0,
        )

    async def stream(self, messages: list[dict], **kwargs: Any) -> AsyncIterator[CompletionChunk]:
        result = await self.complete(messages, **kwargs)
        yield CompletionChunk(
            content=result.content,
            model=result.model,
            provider="onnx",
            done=True,
            usage=result.usage,
        )

    async def health_check(self) -> bool:
        try:
            self._load_model()
            return True
        except Exception:
            return False

    def supports_tools(self) -> bool:
        return False

    def supports_vision(self) -> bool:
        return False

    def estimated_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        return 0.0
