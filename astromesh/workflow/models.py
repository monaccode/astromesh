# astromesh/workflow/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StepType(str, Enum):
    AGENT = "agent"
    TOOL = "tool"
    SWITCH = "switch"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class RetryConfig:
    max_attempts: int = 1
    backoff: str = "fixed"  # "fixed" | "exponential"
    initial_delay_seconds: float = 1.0


@dataclass
class StepSpec:
    name: str
    agent: str | None = None
    tool: str | None = None
    switch: list[dict] | None = None
    input_template: str | None = None
    arguments: dict[str, Any] | None = None
    context_transform: str | None = None
    retry: RetryConfig | None = None
    timeout_seconds: int | None = None
    on_error: str | None = None  # step name to goto, or "fail"

    def __post_init__(self):
        # Coerce retry dict to RetryConfig
        if isinstance(self.retry, dict):
            self.retry = RetryConfig(**self.retry)
        # Validate exactly one step type
        type_count = sum(1 for x in [self.agent, self.tool, self.switch] if x is not None)
        if type_count != 1:
            raise ValueError(
                f"Step '{self.name}' must have exactly one of: agent, tool, switch "
                f"(got {type_count})"
            )

    @property
    def step_type(self) -> StepType:
        if self.agent is not None:
            return StepType.AGENT
        if self.tool is not None:
            return StepType.TOOL
        return StepType.SWITCH


@dataclass
class StepResult:
    name: str
    status: StepStatus
    output: Any = None
    error: str | None = None
    duration_ms: float | None = None


@dataclass
class WorkflowSpec:
    name: str
    trigger: str = "api"
    timeout_seconds: int = 300
    steps: list[StepSpec] = field(default_factory=list)
    observability: dict[str, Any] = field(default_factory=dict)
    version: str = "0.1.0"
    namespace: str = "default"
    description: str = ""

    def __post_init__(self):
        names = [s.name for s in self.steps]
        if len(names) != len(set(names)):
            dupes = [n for n in names if names.count(n) > 1]
            raise ValueError(f"Duplicate step names: {set(dupes)}")

    def get_step(self, name: str) -> StepSpec | None:
        for s in self.steps:
            if s.name == name:
                return s
        return None


@dataclass
class WorkflowRunResult:
    workflow_name: str
    status: str  # "completed" | "failed" | "timed_out"
    steps: dict[str, StepResult] = field(default_factory=dict)
    output: Any = None
    trace: dict | None = None
    duration_ms: float | None = None
