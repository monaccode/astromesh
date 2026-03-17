"""RunResult and StreamEvent types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunResult:
    """Result of an agent execution."""

    answer: str
    steps: list[dict]
    trace: dict | None
    cost: float
    tokens: dict[str, int]
    latency_ms: float
    model: str
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_runtime(cls, runtime_result: dict) -> RunResult:
        """Build RunResult from the dict returned by AgentRuntime.run()."""
        trace = runtime_result.get("trace")
        cost = 0.0
        input_tokens = 0
        output_tokens = 0
        latency_ms = 0.0
        model = ""

        if trace and isinstance(trace, dict):
            spans = trace.get("spans", [])
            for span in spans:
                attrs = span.get("attributes", {})
                if span.get("name") == "llm.complete":
                    cost += attrs.get("cost", 0.0)
                    input_tokens += attrs.get("input_tokens", 0)
                    output_tokens += attrs.get("output_tokens", 0)
                    model = attrs.get("model", model)
                if span.get("parent_span_id") is None:
                    latency_ms = span.get("duration_ms", 0.0)

        return cls(
            answer=runtime_result.get("answer", ""),
            steps=runtime_result.get("steps", []),
            trace=trace,
            cost=cost,
            tokens={"input": input_tokens, "output": output_tokens},
            latency_ms=latency_ms,
            model=model,
        )


@dataclass
class StreamEvent:
    """Event emitted during agent streaming."""

    type: str  # "step" | "token" | "done"
    step: dict | None = None
    content: str | None = None
    result: RunResult | None = None
