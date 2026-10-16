"""RunResult and StreamEvent types."""

from __future__ import annotations

from dataclasses import dataclass, field

from astromesh.api.usage import usage_from_trace


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
    #: True when a guardrail blocked the run; `answer` is then the refusal message and
    #: `guardrail` says which rule ({direction, rule, reason}), never the blocked content.
    blocked: bool = False
    guardrail: dict | None = None
    #: Writes proposed by `mode: propose` tools, not executed (remote runs only).
    propuestas: list[dict] = field(default_factory=list)
    #: Per-(provider, model, role) usage, as core's `usage.by_model`.
    by_model: list[dict] = field(default_factory=list)

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

        usage = usage_from_trace(trace) or {}
        return cls(
            answer=runtime_result.get("answer", ""),
            steps=runtime_result.get("steps", []),
            trace=trace,
            cost=cost,
            tokens={"input": input_tokens, "output": output_tokens},
            latency_ms=latency_ms,
            model=model,
            blocked=bool(runtime_result.get("blocked")),
            guardrail=runtime_result.get("guardrail"),
            propuestas=runtime_result.get("propuestas") or [],
            by_model=usage.get("by_model") or [],
        )


@dataclass
class StreamEvent:
    """Event emitted during agent streaming."""

    type: str  # "step" | "token" | "done"
    step: dict | None = None
    content: str | None = None
    result: RunResult | None = None
