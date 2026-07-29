# astromesh/workflow/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class StepType(StrEnum):
    AGENT = "agent"
    TOOL = "tool"
    SWITCH = "switch"
    WAIT = "wait"
    APPROVAL = "approval"
    PARALLEL = "parallel"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    SKIPPED = "skipped"
    ERROR = "error"
    SUSPENDED = "suspended"


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
    wait: dict | None = None
    approval: dict | None = None
    input_template: str | None = None
    arguments: dict[str, Any] | None = None
    context_transform: str | None = None
    retry: RetryConfig | None = None
    timeout_seconds: int | None = None
    on_error: str | None = None  # step name to goto, "continue", or "fail"
    when: str | None = None
    strict_conditions: bool = False
    parallel: list[StepSpec] | None = None

    def __post_init__(self):
        # Coerce retry dict to RetryConfig
        if isinstance(self.retry, dict):
            self.retry = RetryConfig(**self.retry)
        # Los sub-pasos pueden venir como dicts (YAML) o ya construidos (compilador).
        if self.parallel is not None:
            self.parallel = [p if isinstance(p, StepSpec) else StepSpec(**p) for p in self.parallel]
        # Validate exactly one step type
        type_count = sum(
            1
            for x in [self.agent, self.tool, self.switch, self.wait, self.approval, self.parallel]
            if x is not None
        )
        if type_count != 1:
            raise ValueError(
                f"Step '{self.name}' must have exactly one of: agent, tool, switch, wait, "
                f"approval, parallel (got {type_count})"
            )

    @property
    def step_type(self) -> StepType:
        if self.agent is not None:
            return StepType.AGENT
        if self.tool is not None:
            return StepType.TOOL
        if self.wait is not None:
            return StepType.WAIT
        if self.approval is not None:
            return StepType.APPROVAL
        if self.parallel is not None:
            return StepType.PARALLEL
        return StepType.SWITCH


@dataclass
class StepResult:
    name: str
    status: StepStatus
    output: Any = None
    error: str | None = None
    duration_ms: float | None = None
    # None cuando el paso no declara `when`; True/False cuando sí, para que
    # `_drive` lo publique en el slot `when` del contexto.
    condition_matched: bool | None = None


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
    run_id: str | None = None


@dataclass
class WorkflowRun:
    run_id: str
    workflow_name: str
    status: str  # running | suspended | completed | failed | timed_out | expired
    current_index: int
    context: dict = field(default_factory=dict)
    resume_key: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    expires_at: str | None = None
    error: str | None = None
    pending_approval: dict | None = None
