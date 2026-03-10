# Workflow YAML + Dashboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a workflow engine that executes multi-step YAML-defined pipelines (agent steps, tool steps, switch/branching), expose workflow API endpoints, wire the CLI `run --workflow` command, and ship a built-in observability dashboard served from the API.

**Architecture:** A new `astromesh/workflow/` package mirrors the `AgentRuntime` pattern — `WorkflowLoader` reads `*.workflow.yaml` from `config/workflows/`, `WorkflowEngine` stores loaded workflows and orchestrates execution, and `StepExecutor` dispatches individual steps (agent via `runtime.run()`, tool via `tool_registry.execute()`, switch via Jinja2 condition evaluation). Step results accumulate in a `steps` dict accessible as `{{ steps.<name>.output }}` in subsequent Jinja2 templates. Retry uses `asyncio.sleep` with exponential/fixed backoff; timeout uses `asyncio.wait_for`. TracingContext wraps the entire workflow run plus individual steps. The dashboard is a single inline HTML page served by a FastAPI route at `/v1/dashboard/`, consuming existing `/v1/traces/` and `/v1/metrics/` endpoints.

**Tech Stack:** Python 3.12+, Jinja2 (already a dependency), existing `TracingContext`, existing `AgentRuntime`, existing `ToolRegistry`, FastAPI

**Spec:** `docs/superpowers/specs/2026-03-10-astromesh-ecosystem-design.md`

**Depends on:** Sub-projects 1-3 (Built-in Tools + Observability, CLI, Multi-agent Enhanced) — all complete

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `astromesh/workflow/__init__.py` | `WorkflowEngine` class — loads workflows, executes by name |
| `astromesh/workflow/models.py` | Dataclasses: `WorkflowSpec`, `StepSpec`, `StepResult`, `RetryConfig`, `WorkflowRunResult` |
| `astromesh/workflow/executor.py` | `StepExecutor` — dispatches agent/tool/switch steps, handles retry + timeout |
| `astromesh/workflow/loader.py` | `WorkflowLoader` — reads and validates `*.workflow.yaml` files |
| `astromesh/api/routes/workflows.py` | API routes: run, list, get workflows |
| `astromesh/api/routes/dashboard.py` | Serves inline HTML dashboard at `/v1/dashboard/` |
| `config/workflows/example.workflow.yaml` | Example workflow for testing/documentation |
| `tests/test_workflow_models.py` | Unit tests for workflow dataclasses |
| `tests/test_workflow_loader.py` | Unit tests for YAML loading and validation |
| `tests/test_workflow_executor.py` | Unit tests for step execution (agent, tool, switch) |
| `tests/test_workflow_engine.py` | Integration tests for full workflow runs |
| `tests/test_workflow_api.py` | API route tests |
| `tests/test_dashboard_api.py` | Dashboard route tests |
| `tests/test_cli_run_workflow.py` | CLI `run --workflow` tests |

### Modified Files

| File | Changes |
|------|---------|
| `astromesh/api/main.py` | Mount `workflows.router` and `dashboard.router` |
| `cli/commands/run.py` | Replace stub with actual `POST /v1/workflows/{name}/run` call |

---

## Chunk 1: Models + Loader

### Task 1: Workflow dataclasses

**Files:**
- Create: `astromesh/workflow/models.py`
- Test: `tests/test_workflow_models.py`

- [ ] **Step 1: Write failing tests for workflow dataclasses**

```python
# tests/test_workflow_models.py
import pytest
from astromesh.workflow.models import (
    WorkflowSpec,
    StepSpec,
    StepResult,
    RetryConfig,
    WorkflowRunResult,
    StepType,
    StepStatus,
)


class TestRetryConfig:
    def test_defaults(self):
        rc = RetryConfig()
        assert rc.max_attempts == 1
        assert rc.backoff == "fixed"
        assert rc.initial_delay_seconds == 1.0

    def test_exponential(self):
        rc = RetryConfig(max_attempts=3, backoff="exponential", initial_delay_seconds=2.0)
        assert rc.max_attempts == 3
        assert rc.backoff == "exponential"


class TestStepSpec:
    def test_agent_step(self):
        step = StepSpec(
            name="research",
            agent="web-researcher",
            input_template="{{ trigger.query }}",
        )
        assert step.step_type == StepType.AGENT
        assert step.agent == "web-researcher"

    def test_tool_step(self):
        step = StepSpec(
            name="store",
            tool="cache_store",
            arguments={"key": "k1", "value": "v1"},
        )
        assert step.step_type == StepType.TOOL

    def test_switch_step(self):
        step = StepSpec(
            name="decide",
            switch=[
                {"when": "{{ steps.qualify.output.data.score > 7 }}", "goto": "send-email"},
                {"default": True, "goto": "log-skip"},
            ],
        )
        assert step.step_type == StepType.SWITCH

    def test_invalid_step_raises(self):
        """A step with no agent, tool, or switch is invalid."""
        with pytest.raises(ValueError, match="must have exactly one"):
            StepSpec(name="broken")

    def test_retry_config_from_dict(self):
        step = StepSpec(
            name="s1",
            agent="a1",
            input_template="hi",
            retry={"max_attempts": 3, "backoff": "exponential", "initial_delay_seconds": 2.0},
        )
        assert step.retry.max_attempts == 3
        assert step.retry.backoff == "exponential"


class TestStepResult:
    def test_success(self):
        sr = StepResult(name="research", status=StepStatus.SUCCESS, output={"answer": "hello"})
        assert sr.status == StepStatus.SUCCESS
        assert sr.output["answer"] == "hello"
        assert sr.error is None

    def test_error(self):
        sr = StepResult(name="research", status=StepStatus.ERROR, error="timeout")
        assert sr.status == StepStatus.ERROR


class TestWorkflowSpec:
    def test_basic_workflow(self):
        wf = WorkflowSpec(
            name="test-wf",
            trigger="api",
            timeout_seconds=300,
            steps=[
                StepSpec(name="s1", agent="a1", input_template="{{ trigger.query }}"),
            ],
        )
        assert wf.name == "test-wf"
        assert wf.trigger == "api"
        assert len(wf.steps) == 1

    def test_step_lookup_by_name(self):
        wf = WorkflowSpec(
            name="test-wf",
            trigger="api",
            steps=[
                StepSpec(name="s1", agent="a1", input_template="hi"),
                StepSpec(name="s2", agent="a2", input_template="bye"),
            ],
        )
        assert wf.get_step("s1").agent == "a1"
        assert wf.get_step("s2").agent == "a2"
        assert wf.get_step("nonexistent") is None

    def test_duplicate_step_names_raises(self):
        with pytest.raises(ValueError, match="[Dd]uplicate"):
            WorkflowSpec(
                name="test-wf",
                trigger="api",
                steps=[
                    StepSpec(name="s1", agent="a1", input_template="hi"),
                    StepSpec(name="s1", agent="a2", input_template="bye"),
                ],
            )


class TestWorkflowRunResult:
    def test_basic(self):
        result = WorkflowRunResult(
            workflow_name="test-wf",
            status="completed",
            steps={"s1": StepResult(name="s1", status=StepStatus.SUCCESS, output={"answer": "ok"})},
            output={"answer": "ok"},
        )
        assert result.workflow_name == "test-wf"
        assert result.status == "completed"
        assert "s1" in result.steps
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workflow_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'astromesh.workflow'`

- [ ] **Step 3: Implement workflow dataclasses**

```python
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
```

Create the package init file:

```python
# astromesh/workflow/__init__.py
```

(Will be populated in Task 5 with `WorkflowEngine`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_workflow_models.py -v`
Expected: All pass

---

### Task 2: Workflow YAML loader

**Files:**
- Create: `astromesh/workflow/loader.py`
- Test: `tests/test_workflow_loader.py`

- [ ] **Step 1: Write failing tests for WorkflowLoader**

```python
# tests/test_workflow_loader.py
import pytest
from astromesh.workflow.loader import WorkflowLoader
from astromesh.workflow.models import WorkflowSpec, StepType


@pytest.fixture
def workflows_dir(tmp_path):
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    return wf_dir


def _write_workflow(wf_dir, name, content):
    (wf_dir / f"{name}.workflow.yaml").write_text(content)


class TestWorkflowLoader:
    def test_load_empty_dir(self, workflows_dir):
        loader = WorkflowLoader(str(workflows_dir))
        workflows = loader.load_all()
        assert workflows == {}

    def test_load_basic_workflow(self, workflows_dir):
        _write_workflow(workflows_dir, "test", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: test-wf
  version: "0.1.0"
spec:
  trigger: api
  timeout_seconds: 120
  steps:
    - name: greet
      agent: greeter
      input: "{{ trigger.query }}"
""")
        loader = WorkflowLoader(str(workflows_dir))
        workflows = loader.load_all()
        assert "test-wf" in workflows
        wf = workflows["test-wf"]
        assert isinstance(wf, WorkflowSpec)
        assert wf.trigger == "api"
        assert wf.timeout_seconds == 120
        assert len(wf.steps) == 1
        assert wf.steps[0].step_type == StepType.AGENT

    def test_load_workflow_with_tool_step(self, workflows_dir):
        _write_workflow(workflows_dir, "tool-wf", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: tool-wf
spec:
  steps:
    - name: store
      tool: cache_store
      arguments:
        key: "test-key"
        value: "test-value"
""")
        loader = WorkflowLoader(str(workflows_dir))
        workflows = loader.load_all()
        wf = workflows["tool-wf"]
        assert wf.steps[0].step_type == StepType.TOOL
        assert wf.steps[0].arguments["key"] == "test-key"

    def test_load_workflow_with_switch_step(self, workflows_dir):
        _write_workflow(workflows_dir, "switch-wf", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: switch-wf
spec:
  steps:
    - name: check
      agent: checker
      input: "{{ trigger.query }}"
    - name: decide
      switch:
        - when: "{{ steps.check.output.score > 5 }}"
          goto: high
        - default: true
          goto: low
    - name: high
      agent: high-handler
      input: "high path"
    - name: low
      agent: low-handler
      input: "low path"
""")
        loader = WorkflowLoader(str(workflows_dir))
        workflows = loader.load_all()
        wf = workflows["switch-wf"]
        assert wf.steps[1].step_type == StepType.SWITCH
        assert len(wf.steps[1].switch) == 2

    def test_load_workflow_with_retry(self, workflows_dir):
        _write_workflow(workflows_dir, "retry-wf", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: retry-wf
spec:
  steps:
    - name: flaky
      agent: flaky-agent
      input: "{{ trigger.query }}"
      retry:
        max_attempts: 3
        backoff: exponential
        initial_delay_seconds: 2
      timeout_seconds: 30
      on_error: fallback
    - name: fallback
      agent: fallback-agent
      input: "error occurred"
""")
        loader = WorkflowLoader(str(workflows_dir))
        workflows = loader.load_all()
        wf = workflows["retry-wf"]
        step = wf.steps[0]
        assert step.retry.max_attempts == 3
        assert step.retry.backoff == "exponential"
        assert step.timeout_seconds == 30
        assert step.on_error == "fallback"

    def test_invalid_kind_skipped(self, workflows_dir):
        _write_workflow(workflows_dir, "agent", """
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: not-a-workflow
spec:
  identity:
    description: "This is an agent, not a workflow"
""")
        loader = WorkflowLoader(str(workflows_dir))
        workflows = loader.load_all()
        assert workflows == {}

    def test_missing_dir_returns_empty(self, tmp_path):
        loader = WorkflowLoader(str(tmp_path / "nonexistent"))
        workflows = loader.load_all()
        assert workflows == {}

    def test_load_single_workflow(self, workflows_dir):
        _write_workflow(workflows_dir, "single", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: single-wf
spec:
  steps:
    - name: do-thing
      agent: doer
      input: "{{ trigger.query }}"
""")
        loader = WorkflowLoader(str(workflows_dir))
        wf = loader.load_file(workflows_dir / "single.workflow.yaml")
        assert wf.name == "single-wf"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workflow_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'astromesh.workflow.loader'`

- [ ] **Step 3: Implement WorkflowLoader**

```python
# astromesh/workflow/loader.py
from __future__ import annotations

from pathlib import Path

import yaml

from astromesh.workflow.models import RetryConfig, StepSpec, WorkflowSpec


class WorkflowLoader:
    """Loads *.workflow.yaml files from a directory into WorkflowSpec instances."""

    def __init__(self, workflows_dir: str):
        self._dir = Path(workflows_dir)

    def load_all(self) -> dict[str, WorkflowSpec]:
        """Load all workflow YAML files from the directory. Returns {name: WorkflowSpec}."""
        if not self._dir.exists():
            return {}
        workflows: dict[str, WorkflowSpec] = {}
        for f in self._dir.glob("*.workflow.yaml"):
            try:
                wf = self.load_file(f)
                workflows[wf.name] = wf
            except Exception:
                continue  # skip invalid files
        return workflows

    def load_file(self, path: Path) -> WorkflowSpec:
        """Load a single workflow YAML file."""
        raw = yaml.safe_load(path.read_text())
        if raw.get("kind") != "Workflow":
            raise ValueError(f"Expected kind: Workflow, got: {raw.get('kind')}")
        return self._parse(raw)

    def _parse(self, raw: dict) -> WorkflowSpec:
        metadata = raw.get("metadata", {})
        spec = raw.get("spec", {})
        steps = []
        for step_raw in spec.get("steps", []):
            steps.append(self._parse_step(step_raw))
        return WorkflowSpec(
            name=metadata["name"],
            version=metadata.get("version", "0.1.0"),
            namespace=metadata.get("namespace", "default"),
            description=spec.get("description", ""),
            trigger=spec.get("trigger", "api"),
            timeout_seconds=spec.get("timeout_seconds", 300),
            steps=steps,
            observability=spec.get("observability", {}),
        )

    def _parse_step(self, raw: dict) -> StepSpec:
        retry_raw = raw.get("retry")
        retry = RetryConfig(**retry_raw) if retry_raw else None
        return StepSpec(
            name=raw["name"],
            agent=raw.get("agent"),
            tool=raw.get("tool"),
            switch=raw.get("switch"),
            input_template=raw.get("input"),
            arguments=raw.get("arguments"),
            context_transform=raw.get("context_transform"),
            retry=retry,
            timeout_seconds=raw.get("timeout_seconds"),
            on_error=raw.get("on_error"),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_workflow_loader.py -v`
Expected: All pass

---

### Task 3: Example workflow YAML + updated workflow template

**Files:**
- Create: `config/workflows/example.workflow.yaml`
- Modify: `cli/templates/workflow.yaml.j2`

- [ ] **Step 1: Create example workflow**

```yaml
# config/workflows/example.workflow.yaml
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: lead-qualification
  version: "0.1.0"
  namespace: default

spec:
  description: "Qualify incoming leads through research and scoring"
  trigger: api
  timeout_seconds: 300

  steps:
    - name: research
      agent: web-researcher
      input: "{{ trigger.query }}"

    - name: qualify
      agent: sales-qualifier
      input: "{{ steps.research.output }}"
      retry:
        max_attempts: 3
        backoff: exponential
        initial_delay_seconds: 2
      timeout_seconds: 60
      on_error: log-and-skip

    - name: decide
      switch:
        - when: "{{ steps.qualify.output.data.score > 7 }}"
          goto: notify
        - default: true
          goto: log-and-skip

    - name: notify
      agent: email-composer
      input: "{{ steps.qualify.output }}"

    - name: log-and-skip
      tool: cache_store
      arguments:
        key: "skipped_{{ trigger.id }}"
        value: "{{ steps.qualify.output }}"

  observability:
    collector: internal
```

- [ ] **Step 2: Update workflow template to match full schema**

```jinja2
{# cli/templates/workflow.yaml.j2 #}
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: {{ name }}
  version: "0.1.0"
  namespace: default

spec:
  description: "{{ description }}"
  trigger: api
  timeout_seconds: 300

  steps: []
  # Define workflow steps here, for example:
  # steps:
  #   - name: step-1
  #     agent: my-agent
  #     input: "{{ '{{' }} trigger.query {{ '}}' }}"
  #   - name: step-2
  #     agent: another-agent
  #     input: "{{ '{{' }} steps.step-1.output {{ '}}' }}"
  #   - name: decide
  #     switch:
  #       - when: "{{ '{{' }} steps.step-1.output.score > 5 {{ '}}' }}"
  #         goto: step-3
  #       - default: true
  #         goto: step-4

  observability:
    collector: internal
```

---

## Chunk 2: Step Executor + Engine

### Task 4: StepExecutor — agent, tool, and switch step dispatch

**Files:**
- Create: `astromesh/workflow/executor.py`
- Test: `tests/test_workflow_executor.py`

- [ ] **Step 1: Write failing tests for StepExecutor**

```python
# tests/test_workflow_executor.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from astromesh.workflow.executor import StepExecutor
from astromesh.workflow.models import StepSpec, StepResult, StepStatus, RetryConfig


@pytest.fixture
def mock_runtime():
    runtime = AsyncMock()
    runtime.run = AsyncMock(return_value={"answer": "researched data", "steps": []})
    return runtime


@pytest.fixture
def mock_tool_registry():
    registry = AsyncMock()
    registry.execute = AsyncMock(return_value={"result": "stored"})
    return registry


@pytest.fixture
def executor(mock_runtime, mock_tool_registry):
    return StepExecutor(runtime=mock_runtime, tool_registry=mock_tool_registry)


class TestAgentStep:
    async def test_basic_agent_step(self, executor, mock_runtime):
        step = StepSpec(name="research", agent="web-researcher", input_template="{{ trigger.query }}")
        ctx = {"trigger": {"query": "Tell me about Acme Corp"}, "steps": {}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS
        assert result.output == {"answer": "researched data", "steps": []}
        mock_runtime.run.assert_called_once_with(
            "web-researcher", "Tell me about Acme Corp", session_id=pytest.approx(str, abs=100)
        )

    async def test_agent_step_with_step_reference(self, executor, mock_runtime):
        step = StepSpec(name="qualify", agent="qualifier", input_template="{{ steps.research.output }}")
        ctx = {
            "trigger": {},
            "steps": {"research": {"output": {"answer": "data about Acme"}}},
        }
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS

    async def test_agent_step_error(self, executor, mock_runtime):
        mock_runtime.run.side_effect = Exception("agent crashed")
        step = StepSpec(name="broken", agent="bad-agent", input_template="go")
        ctx = {"trigger": {}, "steps": {}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.ERROR
        assert "agent crashed" in result.error


class TestToolStep:
    async def test_basic_tool_step(self, executor, mock_tool_registry):
        step = StepSpec(name="store", tool="cache_store", arguments={"key": "k", "value": "v"})
        ctx = {"trigger": {}, "steps": {}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS
        assert result.output == {"result": "stored"}

    async def test_tool_step_with_template_args(self, executor, mock_tool_registry):
        step = StepSpec(
            name="store",
            tool="cache_store",
            arguments={"key": "lead_{{ trigger.id }}", "value": "{{ steps.prev.output }}"},
        )
        ctx = {"trigger": {"id": "123"}, "steps": {"prev": {"output": "some data"}}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS
        # Verify arguments were template-rendered
        call_args = mock_tool_registry.execute.call_args
        assert call_args[0][1]["key"] == "lead_123"


class TestSwitchStep:
    async def test_switch_when_true(self, executor):
        step = StepSpec(
            name="decide",
            switch=[
                {"when": "{{ steps.score.output.value > 7 }}", "goto": "high"},
                {"default": True, "goto": "low"},
            ],
        )
        ctx = {"trigger": {}, "steps": {"score": {"output": {"value": 9}}}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS
        assert result.output == {"goto": "high"}

    async def test_switch_default(self, executor):
        step = StepSpec(
            name="decide",
            switch=[
                {"when": "{{ steps.score.output.value > 7 }}", "goto": "high"},
                {"default": True, "goto": "low"},
            ],
        )
        ctx = {"trigger": {}, "steps": {"score": {"output": {"value": 3}}}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS
        assert result.output == {"goto": "low"}

    async def test_switch_no_match_no_default(self, executor):
        step = StepSpec(
            name="decide",
            switch=[{"when": "{{ False }}", "goto": "never"}],
        )
        ctx = {"trigger": {}, "steps": {}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS
        assert result.output == {"goto": None}


class TestRetry:
    async def test_retry_on_failure(self, executor, mock_runtime):
        call_count = 0

        async def flaky_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("transient error")
            return {"answer": "success", "steps": []}

        mock_runtime.run = flaky_run
        step = StepSpec(
            name="flaky",
            agent="flaky-agent",
            input_template="go",
            retry=RetryConfig(max_attempts=3, backoff="fixed", initial_delay_seconds=0.01),
        )
        ctx = {"trigger": {}, "steps": {}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS
        assert call_count == 3

    async def test_retry_exhausted(self, executor, mock_runtime):
        mock_runtime.run = AsyncMock(side_effect=Exception("always fails"))
        step = StepSpec(
            name="doomed",
            agent="bad-agent",
            input_template="go",
            retry=RetryConfig(max_attempts=2, backoff="fixed", initial_delay_seconds=0.01),
        )
        ctx = {"trigger": {}, "steps": {}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.ERROR
        assert mock_runtime.run.call_count == 2


class TestTimeout:
    async def test_step_timeout(self, executor, mock_runtime):
        async def slow_run(*args, **kwargs):
            await asyncio.sleep(10)
            return {"answer": "too late"}

        mock_runtime.run = slow_run
        step = StepSpec(
            name="slow",
            agent="slow-agent",
            input_template="go",
            timeout_seconds=1,
        )
        ctx = {"trigger": {}, "steps": {}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.ERROR
        assert "timeout" in result.error.lower() or "timed out" in result.error.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workflow_executor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'astromesh.workflow.executor'`

- [ ] **Step 3: Implement StepExecutor**

```python
# astromesh/workflow/executor.py
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from jinja2 import Environment, BaseLoader, Undefined

from astromesh.workflow.models import StepSpec, StepResult, StepStatus, StepType


class _SilentUndefined(Undefined):
    def __str__(self):
        return ""

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return False


class StepExecutor:
    """Dispatches individual workflow steps: agent, tool, or switch."""

    def __init__(self, runtime, tool_registry):
        self._runtime = runtime
        self._tool_registry = tool_registry
        self._jinja = Environment(loader=BaseLoader(), undefined=_SilentUndefined)

    async def execute_step(self, step: StepSpec, context: dict[str, Any]) -> StepResult:
        """Execute a single step with retry and timeout handling."""
        max_attempts = step.retry.max_attempts if step.retry else 1
        backoff = step.retry.backoff if step.retry else "fixed"
        delay = step.retry.initial_delay_seconds if step.retry else 1.0

        last_error: str | None = None
        for attempt in range(max_attempts):
            try:
                coro = self._dispatch(step, context)
                if step.timeout_seconds:
                    result = await asyncio.wait_for(coro, timeout=step.timeout_seconds)
                else:
                    result = await coro
                return result
            except asyncio.TimeoutError:
                last_error = f"Step '{step.name}' timed out after {step.timeout_seconds}s"
            except Exception as exc:
                last_error = str(exc)

            if attempt < max_attempts - 1:
                sleep_time = delay * (2**attempt if backoff == "exponential" else 1)
                await asyncio.sleep(sleep_time)

        return StepResult(name=step.name, status=StepStatus.ERROR, error=last_error)

    async def _dispatch(self, step: StepSpec, context: dict[str, Any]) -> StepResult:
        start = time.time()
        if step.step_type == StepType.AGENT:
            return await self._run_agent(step, context, start)
        elif step.step_type == StepType.TOOL:
            return await self._run_tool(step, context, start)
        elif step.step_type == StepType.SWITCH:
            return await self._run_switch(step, context, start)
        raise ValueError(f"Unknown step type for step '{step.name}'")

    async def _run_agent(self, step: StepSpec, ctx: dict, start: float) -> StepResult:
        rendered_input = self._render(step.input_template or "", ctx)
        session_id = str(uuid.uuid4())
        result = await self._runtime.run(step.agent, rendered_input, session_id=session_id)
        elapsed = (time.time() - start) * 1000
        return StepResult(
            name=step.name, status=StepStatus.SUCCESS, output=result, duration_ms=elapsed
        )

    async def _run_tool(self, step: StepSpec, ctx: dict, start: float) -> StepResult:
        arguments = {}
        for key, val in (step.arguments or {}).items():
            if isinstance(val, str):
                arguments[key] = self._render(val, ctx)
            else:
                arguments[key] = val
        result = await self._tool_registry.execute(step.tool, arguments)
        elapsed = (time.time() - start) * 1000
        return StepResult(
            name=step.name, status=StepStatus.SUCCESS, output=result, duration_ms=elapsed
        )

    async def _run_switch(self, step: StepSpec, ctx: dict, start: float) -> StepResult:
        goto: str | None = None
        for branch in step.switch:
            if branch.get("default"):
                goto = branch["goto"]
                break
            condition = branch.get("when", "")
            rendered = self._render(condition, ctx).strip()
            if rendered.lower() in ("true", "1", "yes"):
                goto = branch["goto"]
                break
        elapsed = (time.time() - start) * 1000
        return StepResult(
            name=step.name, status=StepStatus.SUCCESS, output={"goto": goto}, duration_ms=elapsed
        )

    def _render(self, template_str: str, context: dict) -> str:
        return self._jinja.from_string(template_str).render(**context)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_workflow_executor.py -v`
Expected: All pass

---

### Task 5: WorkflowEngine — orchestrate full workflow runs

**Files:**
- Create/Update: `astromesh/workflow/__init__.py`
- Test: `tests/test_workflow_engine.py`

- [ ] **Step 1: Write failing tests for WorkflowEngine**

```python
# tests/test_workflow_engine.py
import pytest
from unittest.mock import AsyncMock

from astromesh.workflow import WorkflowEngine
from astromesh.workflow.models import WorkflowRunResult


@pytest.fixture
def workflows_dir(tmp_path):
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    return wf_dir


def _write_workflow(wf_dir, name, content):
    (wf_dir / f"{name}.workflow.yaml").write_text(content)


@pytest.fixture
def mock_runtime():
    runtime = AsyncMock()
    runtime.run = AsyncMock(return_value={"answer": "agent result", "steps": []})
    return runtime


@pytest.fixture
def mock_tool_registry():
    registry = AsyncMock()
    registry.execute = AsyncMock(return_value={"result": "stored"})
    return registry


class TestWorkflowEngine:
    async def test_bootstrap_loads_workflows(self, workflows_dir, mock_runtime, mock_tool_registry):
        _write_workflow(workflows_dir, "test", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: test-wf
spec:
  steps:
    - name: s1
      agent: a1
      input: "hello"
""")
        engine = WorkflowEngine(
            workflows_dir=str(workflows_dir),
            runtime=mock_runtime,
            tool_registry=mock_tool_registry,
        )
        await engine.bootstrap()
        assert "test-wf" in engine.list_workflows()

    async def test_list_workflows(self, workflows_dir, mock_runtime, mock_tool_registry):
        _write_workflow(workflows_dir, "wf1", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: wf-alpha
spec:
  steps:
    - name: s1
      agent: a1
      input: "hi"
""")
        _write_workflow(workflows_dir, "wf2", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: wf-beta
spec:
  steps:
    - name: s1
      agent: a2
      input: "hi"
""")
        engine = WorkflowEngine(
            workflows_dir=str(workflows_dir),
            runtime=mock_runtime,
            tool_registry=mock_tool_registry,
        )
        await engine.bootstrap()
        names = engine.list_workflows()
        assert set(names) == {"wf-alpha", "wf-beta"}

    async def test_run_sequential_steps(self, workflows_dir, mock_runtime, mock_tool_registry):
        _write_workflow(workflows_dir, "seq", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: seq-wf
spec:
  steps:
    - name: step1
      agent: agent1
      input: "{{ trigger.query }}"
    - name: step2
      agent: agent2
      input: "{{ steps.step1.output }}"
""")
        engine = WorkflowEngine(
            workflows_dir=str(workflows_dir),
            runtime=mock_runtime,
            tool_registry=mock_tool_registry,
        )
        await engine.bootstrap()
        result = await engine.run("seq-wf", trigger={"query": "hello"})
        assert isinstance(result, WorkflowRunResult)
        assert result.status == "completed"
        assert "step1" in result.steps
        assert "step2" in result.steps
        assert mock_runtime.run.call_count == 2

    async def test_run_with_switch_goto(self, workflows_dir, mock_runtime, mock_tool_registry):
        mock_runtime.run = AsyncMock(
            return_value={"answer": "ok", "data": {"score": 9}, "steps": []}
        )
        _write_workflow(workflows_dir, "switch", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: switch-wf
spec:
  steps:
    - name: score
      agent: scorer
      input: "{{ trigger.query }}"
    - name: decide
      switch:
        - when: "{{ steps.score.output.data.score > 7 }}"
          goto: high
        - default: true
          goto: low
    - name: high
      agent: high-handler
      input: "high path"
    - name: low
      agent: low-handler
      input: "low path"
""")
        engine = WorkflowEngine(
            workflows_dir=str(workflows_dir),
            runtime=mock_runtime,
            tool_registry=mock_tool_registry,
        )
        await engine.bootstrap()
        result = await engine.run("switch-wf", trigger={"query": "test"})
        assert result.status == "completed"
        # Should have executed: score -> decide -> high (skipping low)
        assert "score" in result.steps
        assert "decide" in result.steps
        assert "high" in result.steps
        assert "low" not in result.steps

    async def test_run_nonexistent_workflow(self, workflows_dir, mock_runtime, mock_tool_registry):
        engine = WorkflowEngine(
            workflows_dir=str(workflows_dir),
            runtime=mock_runtime,
            tool_registry=mock_tool_registry,
        )
        await engine.bootstrap()
        with pytest.raises(ValueError, match="not found"):
            await engine.run("ghost-wf", trigger={})

    async def test_run_on_error_goto(self, workflows_dir, mock_runtime, mock_tool_registry):
        call_count = 0

        async def conditional_run(agent_name, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if agent_name == "bad-agent":
                raise Exception("agent failed")
            return {"answer": "fallback ok", "steps": []}

        mock_runtime.run = conditional_run
        _write_workflow(workflows_dir, "error", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: error-wf
spec:
  steps:
    - name: risky
      agent: bad-agent
      input: "go"
      on_error: fallback
    - name: fallback
      agent: safe-agent
      input: "recover"
""")
        engine = WorkflowEngine(
            workflows_dir=str(workflows_dir),
            runtime=mock_runtime,
            tool_registry=mock_tool_registry,
        )
        await engine.bootstrap()
        result = await engine.run("error-wf", trigger={})
        assert result.status == "completed"
        assert "fallback" in result.steps
        assert result.steps["fallback"].status.value == "success"

    async def test_run_produces_trace(self, workflows_dir, mock_runtime, mock_tool_registry):
        _write_workflow(workflows_dir, "traced", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: traced-wf
spec:
  steps:
    - name: s1
      agent: a1
      input: "hello"
""")
        engine = WorkflowEngine(
            workflows_dir=str(workflows_dir),
            runtime=mock_runtime,
            tool_registry=mock_tool_registry,
        )
        await engine.bootstrap()
        result = await engine.run("traced-wf", trigger={"query": "hi"})
        assert result.trace is not None
        assert "trace_id" in result.trace
        assert len(result.trace["spans"]) >= 2  # workflow.run + step span
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workflow_engine.py -v`
Expected: FAIL — `ImportError: cannot import name 'WorkflowEngine'`

- [ ] **Step 3: Implement WorkflowEngine**

```python
# astromesh/workflow/__init__.py
from __future__ import annotations

import time
from typing import Any

from astromesh.observability.tracing import TracingContext, SpanStatus
from astromesh.workflow.executor import StepExecutor
from astromesh.workflow.loader import WorkflowLoader
from astromesh.workflow.models import (
    StepStatus as WfStepStatus,
    StepType,
    WorkflowRunResult,
    WorkflowSpec,
)


class WorkflowEngine:
    """Loads workflow YAML specs and orchestrates multi-step execution."""

    def __init__(self, workflows_dir: str, runtime, tool_registry):
        self._workflows_dir = workflows_dir
        self._runtime = runtime
        self._tool_registry = tool_registry
        self._workflows: dict[str, WorkflowSpec] = {}
        self._executor: StepExecutor | None = None

    async def bootstrap(self):
        loader = WorkflowLoader(self._workflows_dir)
        self._workflows = loader.load_all()
        self._executor = StepExecutor(
            runtime=self._runtime, tool_registry=self._tool_registry
        )

    def list_workflows(self) -> list[str]:
        return list(self._workflows.keys())

    def get_workflow(self, name: str) -> WorkflowSpec | None:
        return self._workflows.get(name)

    async def run(
        self, workflow_name: str, trigger: dict[str, Any]
    ) -> WorkflowRunResult:
        wf = self._workflows.get(workflow_name)
        if not wf:
            raise ValueError(f"Workflow '{workflow_name}' not found")

        tracing = TracingContext(agent_name=f"workflow:{workflow_name}", session_id="")
        root_span = tracing.start_span(
            "workflow.run", {"workflow": workflow_name, "trigger_type": wf.trigger}
        )

        start = time.time()
        step_results: dict[str, Any] = {}
        context: dict[str, Any] = {"trigger": trigger, "steps": {}}
        status = "completed"

        try:
            # Build step index for goto lookups
            step_index = {s.name: i for i, s in enumerate(wf.steps)}
            i = 0

            while i < len(wf.steps):
                step = wf.steps[i]
                step_span = tracing.start_span(
                    f"step.{step.name}",
                    {"step_type": step.step_type.value},
                    parent_span_id=root_span.span_id,
                )

                result = await self._executor.execute_step(step, context)
                step_results[step.name] = result

                if result.status == WfStepStatus.ERROR:
                    tracing.finish_span(step_span, status=SpanStatus.ERROR)
                    if step.on_error and step.on_error != "fail":
                        # Jump to error handler step
                        context["steps"][step.name] = {
                            "output": result.output,
                            "error": result.error,
                        }
                        if step.on_error in step_index:
                            i = step_index[step.on_error]
                            continue
                    status = "failed"
                    break
                else:
                    tracing.finish_span(step_span)

                # Store result in context for subsequent steps
                context["steps"][step.name] = {"output": result.output}

                # Handle switch goto
                if step.step_type == StepType.SWITCH and result.output:
                    goto = result.output.get("goto")
                    if goto and goto in step_index:
                        i = step_index[goto]
                        continue

                i += 1

        except Exception as exc:
            status = "failed"
            tracing.finish_span(root_span, status=SpanStatus.ERROR)
            elapsed = (time.time() - start) * 1000
            return WorkflowRunResult(
                workflow_name=workflow_name,
                status=status,
                steps=step_results,
                trace=tracing.to_dict(),
                duration_ms=elapsed,
            )

        tracing.finish_span(root_span)
        elapsed = (time.time() - start) * 1000

        # Output is the last executed step's output
        last_step_name = list(step_results.keys())[-1] if step_results else None
        output = step_results[last_step_name].output if last_step_name else None

        return WorkflowRunResult(
            workflow_name=workflow_name,
            status=status,
            steps=step_results,
            output=output,
            trace=tracing.to_dict(),
            duration_ms=elapsed,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_workflow_engine.py -v`
Expected: All pass

---

## Chunk 3: API + CLI Wiring

### Task 6: Workflow API routes

**Files:**
- Create: `astromesh/api/routes/workflows.py`
- Test: `tests/test_workflow_api.py`

- [ ] **Step 1: Write failing tests for workflow API**

```python
# tests/test_workflow_api.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from fastapi import FastAPI
from astromesh.api.routes.workflows import router, set_workflow_engine
from astromesh.workflow.models import WorkflowRunResult, StepResult, StepStatus


def _make_app():
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    return app


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.list_workflows.return_value = ["wf-alpha", "wf-beta"]
    engine.get_workflow.return_value = MagicMock(
        name="wf-alpha",
        version="0.1.0",
        namespace="default",
        description="Test workflow",
        trigger="api",
        timeout_seconds=300,
        steps=[MagicMock(name="s1", step_type=MagicMock(value="agent"))],
    )
    engine.run = AsyncMock(
        return_value=WorkflowRunResult(
            workflow_name="wf-alpha",
            status="completed",
            steps={"s1": StepResult(name="s1", status=StepStatus.SUCCESS, output={"answer": "ok"})},
            output={"answer": "ok"},
            trace={"trace_id": "abc123", "spans": []},
            duration_ms=150.0,
        )
    )
    return engine


class TestWorkflowAPI:
    async def test_list_workflows(self, mock_engine):
        set_workflow_engine(mock_engine)
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert "wf-alpha" in data["workflows"]

    async def test_get_workflow(self, mock_engine):
        set_workflow_engine(mock_engine)
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/workflows/wf-alpha")
        assert resp.status_code == 200

    async def test_get_workflow_not_found(self, mock_engine):
        mock_engine.get_workflow.return_value = None
        set_workflow_engine(mock_engine)
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/workflows/nonexistent")
        assert resp.status_code == 404

    async def test_run_workflow(self, mock_engine):
        set_workflow_engine(mock_engine)
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/v1/workflows/wf-alpha/run", json={"query": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["workflow_name"] == "wf-alpha"

    async def test_run_workflow_not_found(self, mock_engine):
        mock_engine.run = AsyncMock(side_effect=ValueError("Workflow 'ghost' not found"))
        set_workflow_engine(mock_engine)
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/v1/workflows/ghost/run", json={"query": "hi"})
        assert resp.status_code == 404

    async def test_run_workflow_no_engine(self):
        set_workflow_engine(None)
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/v1/workflows/any/run", json={"query": "hi"})
        assert resp.status_code == 503
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workflow_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'astromesh.api.routes.workflows'`

- [ ] **Step 3: Implement workflow API routes**

```python
# astromesh/api/routes/workflows.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/workflows", tags=["workflows"])

_engine = None


def set_workflow_engine(engine) -> None:
    global _engine
    _engine = engine


class WorkflowRunRequest(BaseModel):
    query: str = ""
    trigger: dict[str, Any] | None = None


@router.get("/")
async def list_workflows():
    if not _engine:
        return {"workflows": []}
    return {"workflows": _engine.list_workflows()}


@router.get("/{name}")
async def get_workflow(name: str):
    if not _engine:
        raise HTTPException(status_code=503, detail="Workflow engine not initialized")
    wf = _engine.get_workflow(name)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")
    return {
        "name": wf.name,
        "version": wf.version,
        "namespace": wf.namespace,
        "description": wf.description,
        "trigger": wf.trigger,
        "timeout_seconds": wf.timeout_seconds,
        "steps": [
            {"name": s.name, "type": s.step_type.value}
            for s in wf.steps
        ],
    }


@router.post("/{name}/run")
async def run_workflow(name: str, request: WorkflowRunRequest):
    if not _engine:
        raise HTTPException(status_code=503, detail="Workflow engine not initialized")
    trigger = request.trigger or {"query": request.query}
    try:
        result = await _engine.run(name, trigger=trigger)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "workflow_name": result.workflow_name,
        "status": result.status,
        "output": result.output,
        "steps": {
            k: {"status": v.status.value, "output": v.output, "error": v.error}
            for k, v in result.steps.items()
        },
        "trace": result.trace,
        "duration_ms": result.duration_ms,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_workflow_api.py -v`
Expected: All pass

---

### Task 7: Mount workflow routes in API main

**Files:**
- Modify: `astromesh/api/main.py`

- [ ] **Step 1: Add workflow and dashboard router imports and mount them**

In `astromesh/api/main.py`, add:

```python
# Add to imports:
from astromesh.api.routes import workflows

# Add after existing router mounts:
app.include_router(workflows.router, prefix="/v1")
```

This adds the `/v1/workflows/` endpoints. The `set_workflow_engine()` call will be wired in the daemon bootstrap (same pattern as `agents.set_runtime()`).

- [ ] **Step 2: Verify existing tests still pass**

Run: `uv run pytest tests/test_api.py -v`
Expected: All pass (no regressions)

---

### Task 8: Wire CLI `run --workflow` command

**Files:**
- Modify: `cli/commands/run.py`
- Test: `tests/test_cli_run_workflow.py`

- [ ] **Step 1: Write failing tests for CLI workflow execution**

```python
# tests/test_cli_run_workflow.py
import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


class TestCLIRunWorkflow:
    def test_run_workflow_basic(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "workflow_name": "lead-qual",
            "status": "completed",
            "output": {"answer": "lead is qualified"},
            "steps": {"s1": {"status": "success", "output": {"answer": "ok"}}},
            "duration_ms": 1234.5,
        }
        mock_response.raise_for_status = MagicMock()
        with patch("cli.client.httpx.post", return_value=mock_response) as mock_post:
            result = runner.invoke(
                app, ["run", "lead-qual", "--workflow", "--input", '{"query": "test lead"}']
            )
        assert result.exit_code == 0
        assert "completed" in result.output.lower() or "lead-qual" in result.output
        # Verify correct endpoint was called
        call_url = mock_post.call_args[0][0]
        assert "/v1/workflows/lead-qual/run" in call_url

    def test_run_workflow_json_output(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "workflow_name": "wf1",
            "status": "completed",
            "output": {"answer": "done"},
            "steps": {},
            "duration_ms": 100.0,
        }
        mock_response.raise_for_status = MagicMock()
        with patch("cli.client.httpx.post", return_value=mock_response):
            result = runner.invoke(
                app, ["run", "wf1", "--workflow", "--json", "--input", '{"query": "hi"}']
            )
        assert result.exit_code == 0
        assert "workflow_name" in result.output

    def test_run_workflow_failure(self):
        with patch("cli.client.httpx.post", side_effect=Exception("connection refused")):
            result = runner.invoke(
                app, ["run", "wf1", "--workflow", "--input", '{"query": "hi"}']
            )
        assert result.exit_code == 1

    def test_run_workflow_default_empty_input(self):
        """When --input is not provided, send empty trigger with query from positional arg."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "workflow_name": "wf1",
            "status": "completed",
            "output": {},
            "steps": {},
            "duration_ms": 50.0,
        }
        mock_response.raise_for_status = MagicMock()
        with patch("cli.client.httpx.post", return_value=mock_response) as mock_post:
            result = runner.invoke(app, ["run", "wf1", "hello world", "--workflow"])
        assert result.exit_code == 0
        call_json = mock_post.call_args[1].get("json") or mock_post.call_args.kwargs.get("json")
        assert call_json["query"] == "hello world"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_run_workflow.py -v`
Expected: FAIL — output still says "not yet implemented"

- [ ] **Step 3: Update `cli/commands/run.py` to execute workflows**

```python
# cli/commands/run.py
"""astromeshctl run — Execute agents and workflows."""

import json
import uuid
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from cli.client import api_post_with_timeout
from cli.output import console, print_error, print_json


def run_command(
    name: str = typer.Argument(..., help="Agent or workflow name to run"),
    query: str = typer.Argument("", help="Query to send to the agent"),
    session: Optional[str] = typer.Option(None, "--session", help="Session ID (auto-generated if not set)"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON response"),
    timeout: float = typer.Option(60.0, "--timeout", help="Request timeout in seconds"),
    workflow: bool = typer.Option(False, "--workflow", help="Run as workflow instead of agent"),
    input_data: Optional[str] = typer.Option(None, "--input", help="Workflow input data (JSON)"),
) -> None:
    """Execute an agent with a query or run a workflow."""
    if workflow:
        _run_workflow(name, query, input_data, json_output, timeout)
        return

    if not query:
        print_error("Query is required when running an agent.")
        raise typer.Exit(code=1)

    session_id = session or str(uuid.uuid4())

    try:
        data = api_post_with_timeout(
            f"/v1/agents/{name}/run",
            json={"query": query, "session_id": session_id},
            timeout=timeout,
        )
    except Exception as e:
        print_error(f"Failed to run agent '{name}': {e}")
        raise typer.Exit(code=1)

    if json_output:
        print_json(data)
        return

    response_text = data.get("response", "")
    trace_id = data.get("trace_id", "N/A")
    tokens = data.get("tokens_used", "N/A")

    console.print(
        Panel(
            response_text,
            title=f"[cyan]{name}[/cyan]",
            subtitle=f"trace: {trace_id} | tokens: {tokens}",
            border_style="blue",
        )
    )


def _run_workflow(
    name: str, query: str, input_data: str | None, json_output: bool, timeout: float
) -> None:
    """Execute a workflow via the API."""
    if input_data:
        try:
            trigger = json.loads(input_data)
        except json.JSONDecodeError as e:
            print_error(f"Invalid JSON in --input: {e}")
            raise typer.Exit(code=1)
        payload = {"trigger": trigger, "query": query}
    else:
        payload = {"query": query}

    try:
        data = api_post_with_timeout(
            f"/v1/workflows/{name}/run",
            json=payload,
            timeout=timeout,
        )
    except Exception as e:
        print_error(f"Failed to run workflow '{name}': {e}")
        raise typer.Exit(code=1)

    if json_output:
        print_json(data)
        return

    status = data.get("status", "unknown")
    duration = data.get("duration_ms", 0)
    output = data.get("output", {})
    steps = data.get("steps", {})

    # Build step summary table
    table = Table(title="Steps", show_header=True)
    table.add_column("Step", style="cyan")
    table.add_column("Status")
    for step_name, step_info in steps.items():
        step_status = step_info.get("status", "unknown")
        style = "green" if step_status == "success" else "red"
        table.add_row(step_name, f"[{style}]{step_status}[/{style}]")

    answer = output.get("answer", str(output)) if isinstance(output, dict) else str(output)
    console.print(
        Panel(
            answer,
            title=f"[cyan]workflow:{name}[/cyan]",
            subtitle=f"status: {status} | {duration:.0f}ms",
            border_style="green" if status == "completed" else "red",
        )
    )
    if steps:
        console.print(table)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_run_workflow.py tests/test_cli_run.py -v`
Expected: All pass (including existing `test_run_workflow_stub` which tests the old stub message — update or remove this test if it now calls the API instead)

**Note:** The existing `test_run_workflow_stub` in `tests/test_cli_run.py` expects the "not yet implemented" message. Update it to either match the new behavior or remove it, since `tests/test_cli_run_workflow.py` now covers workflow execution.

---

## Chunk 4: Dashboard

### Task 9: Dashboard HTML page

**Files:**
- Create: `astromesh/api/routes/dashboard.py`
- Test: `tests/test_dashboard_api.py`

- [ ] **Step 1: Write failing tests for dashboard route**

```python
# tests/test_dashboard_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from astromesh.api.routes.dashboard import router


def _make_app():
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    return app


class TestDashboardAPI:
    async def test_dashboard_returns_html(self):
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/dashboard/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "<html" in resp.text.lower()

    async def test_dashboard_contains_key_elements(self):
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/dashboard/")
        html = resp.text
        # Verify key UI sections exist
        assert "traces" in html.lower() or "Traces" in html
        assert "metrics" in html.lower() or "Metrics" in html
        assert "/v1/traces" in html  # fetches from traces API
        assert "/v1/metrics" in html  # fetches from metrics API

    async def test_dashboard_contains_workflow_section(self):
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/dashboard/")
        html = resp.text
        assert "workflow" in html.lower()

    async def test_dashboard_has_auto_refresh(self):
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/dashboard/")
        html = resp.text
        # Should have some form of auto-refresh (setInterval or similar)
        assert "setInterval" in html or "auto-refresh" in html.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_dashboard_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'astromesh.api.routes.dashboard'`

- [ ] **Step 3: Implement dashboard route with inline HTML**

```python
# astromesh/api/routes/dashboard.py
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Astromesh Dashboard</title>
<style>
  :root {
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #38bdf8;
    --green: #4ade80; --red: #f87171; --yellow: #fbbf24;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: var(--bg); color: var(--text); padding: 1rem; }
  h1 { font-size: 1.5rem; margin-bottom: 1rem; color: var(--accent); }
  h2 { font-size: 1.1rem; margin-bottom: 0.75rem; color: var(--muted); }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }
  .card { background: var(--surface); border: 1px solid var(--border);
          border-radius: 8px; padding: 1rem; overflow: auto; }
  .card.full { grid-column: 1 / -1; }
  .metric-row { display: flex; justify-content: space-between; padding: 0.3rem 0;
                border-bottom: 1px solid var(--border); font-size: 0.9rem; }
  .metric-value { font-weight: 600; color: var(--accent); }
  .trace-item { padding: 0.5rem; border-bottom: 1px solid var(--border);
                cursor: pointer; font-size: 0.85rem; }
  .trace-item:hover { background: var(--border); }
  .trace-item .agent { color: var(--accent); font-weight: 600; }
  .trace-item .meta { color: var(--muted); font-size: 0.75rem; }
  .span-tree { padding-left: 1.2rem; font-size: 0.8rem; display: none; }
  .span-tree.open { display: block; }
  .span { padding: 0.2rem 0; }
  .span .name { color: var(--accent); }
  .span .dur { color: var(--muted); margin-left: 0.5rem; }
  .status-ok { color: var(--green); }
  .status-error { color: var(--red); }
  .status-unset { color: var(--yellow); }
  .workflow-steps { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }
  .step-node { background: var(--bg); border: 1px solid var(--border);
               border-radius: 6px; padding: 0.4rem 0.8rem; font-size: 0.8rem; }
  .step-node.agent { border-color: var(--accent); }
  .step-node.tool { border-color: var(--green); }
  .step-node.switch { border-color: var(--yellow); }
  .arrow { color: var(--muted); align-self: center; }
  .refresh-bar { display: flex; justify-content: space-between; align-items: center;
                 margin-bottom: 1rem; font-size: 0.85rem; color: var(--muted); }
  .refresh-bar button { background: var(--surface); color: var(--text); border: 1px solid var(--border);
                        border-radius: 4px; padding: 0.3rem 0.8rem; cursor: pointer; }
  .refresh-bar button:hover { background: var(--border); }
  #status { font-size: 0.75rem; }
</style>
</head>
<body>
<h1>Astromesh Dashboard</h1>
<div class="refresh-bar">
  <span id="status">Loading...</span>
  <div>
    <label><input type="checkbox" id="auto-refresh" checked> Auto-refresh (10s)</label>
    <button onclick="refresh()">Refresh Now</button>
  </div>
</div>

<div class="grid">
  <div class="card">
    <h2>Counters</h2>
    <div id="counters"><em>No data</em></div>
  </div>
  <div class="card">
    <h2>Histograms</h2>
    <div id="histograms"><em>No data</em></div>
  </div>
</div>

<div class="grid">
  <div class="card full">
    <h2>Workflows</h2>
    <div id="workflows"><em>Loading...</em></div>
  </div>
</div>

<div class="grid">
  <div class="card full">
    <h2>Traces</h2>
    <div id="traces"><em>Loading...</em></div>
  </div>
</div>

<script>
const BASE = window.location.origin;

async function fetchJSON(path) {
  const resp = await fetch(BASE + path);
  if (!resp.ok) return null;
  return resp.json();
}

function renderCounters(data) {
  const el = document.getElementById("counters");
  const counters = data?.counters || {};
  const keys = Object.keys(counters);
  if (!keys.length) { el.innerHTML = "<em>No counters</em>"; return; }
  el.innerHTML = keys.map(k =>
    `<div class="metric-row"><span>${k}</span><span class="metric-value">${counters[k]}</span></div>`
  ).join("");
}

function renderHistograms(data) {
  const el = document.getElementById("histograms");
  const hists = data?.histograms || {};
  const keys = Object.keys(hists);
  if (!keys.length) { el.innerHTML = "<em>No histograms</em>"; return; }
  el.innerHTML = keys.map(k => {
    const h = hists[k];
    return `<div class="metric-row"><span>${k}</span>
      <span class="metric-value">avg=${h.avg?.toFixed(1)} min=${h.min?.toFixed(1)} max=${h.max?.toFixed(1)} n=${h.count}</span></div>`;
  }).join("");
}

function renderWorkflows(data) {
  const el = document.getElementById("workflows");
  const wfs = data?.workflows || [];
  if (!wfs.length) { el.innerHTML = "<em>No workflows loaded</em>"; return; }
  el.innerHTML = wfs.map(name =>
    `<div class="step-node" style="display:inline-block;margin:0.25rem">${name}</div>`
  ).join("");
}

function renderSpanTree(spans) {
  if (!spans || !spans.length) return "";
  return spans.map(s => {
    const dur = s.duration_ms != null ? s.duration_ms.toFixed(1) + "ms" : "...";
    const cls = "status-" + (s.status || "unset");
    return `<div class="span"><span class="name">${s.name}</span><span class="dur">${dur}</span> <span class="${cls}">${s.status}</span></div>`;
  }).join("");
}

function renderTraces(data) {
  const el = document.getElementById("traces");
  const traces = data?.traces || [];
  if (!traces.length) { el.innerHTML = "<em>No traces</em>"; return; }
  el.innerHTML = traces.map((t, i) => {
    const spans = t.spans || [];
    const rootDur = spans[0]?.duration_ms != null ? spans[0].duration_ms.toFixed(0) + "ms" : "?";
    return `<div class="trace-item" onclick="toggleSpans(${i})">
      <span class="agent">${t.agent || "?"}</span>
      <span class="meta">${t.trace_id?.substring(0, 12)}... | ${spans.length} spans | ${rootDur}</span>
      <div class="span-tree" id="spans-${i}">${renderSpanTree(spans)}</div>
    </div>`;
  }).join("");
}

function toggleSpans(i) {
  const el = document.getElementById("spans-" + i);
  el.classList.toggle("open");
}

async function refresh() {
  document.getElementById("status").textContent = "Refreshing...";
  try {
    const [metrics, traces, workflows] = await Promise.all([
      fetchJSON("/v1/metrics/"),
      fetchJSON("/v1/traces/?limit=50"),
      fetchJSON("/v1/workflows"),
    ]);
    renderCounters(metrics);
    renderHistograms(metrics);
    renderTraces(traces);
    renderWorkflows(workflows);
    document.getElementById("status").textContent = "Updated " + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById("status").textContent = "Error: " + e.message;
  }
}

let intervalId = setInterval(refresh, 10000);
document.getElementById("auto-refresh").addEventListener("change", function() {
  if (this.checked) { intervalId = setInterval(refresh, 10000); }
  else { clearInterval(intervalId); }
});

refresh();
</script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_dashboard_api.py -v`
Expected: All pass

---

### Task 10: Mount dashboard route in API main

**Files:**
- Modify: `astromesh/api/main.py`

- [ ] **Step 1: Add dashboard router import and mount**

In `astromesh/api/main.py`, add:

```python
# Add to imports (alongside workflows from Task 7):
from astromesh.api.routes import workflows, dashboard

# Add after workflow router mount:
app.include_router(dashboard.router, prefix="/v1")
```

The final `astromesh/api/main.py` should include these lines among the router mounts:

```python
app.include_router(workflows.router, prefix="/v1")
app.include_router(dashboard.router, prefix="/v1")
```

- [ ] **Step 2: Verify all tests pass**

Run: `uv run pytest tests/test_dashboard_api.py tests/test_workflow_api.py tests/test_api.py -v`
Expected: All pass

---

### Task 11: Update existing test for CLI workflow stub

**Files:**
- Modify: `tests/test_cli_run.py`

- [ ] **Step 1: Update `test_run_workflow_stub` to match new behavior**

The test `test_run_workflow_stub` in `tests/test_cli_run.py` currently expects the "not yet implemented" message. Update it to match the new behavior where `--workflow` calls the API.

```python
# Replace test_run_workflow_stub with:
def test_run_workflow_calls_api():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "workflow_name": "my-workflow",
        "status": "completed",
        "output": {"answer": "done"},
        "steps": {},
        "duration_ms": 100.0,
    }
    mock_response.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_response):
        result = runner.invoke(app, ["run", "my-workflow", "--workflow", "--input", "{}"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run full test suite to verify no regressions**

Run: `uv run pytest tests/test_cli_run.py tests/test_cli_run_workflow.py -v`
Expected: All pass

---

## Summary

| Chunk | Tasks | Files Created | Files Modified | Tests |
|-------|-------|--------------|----------------|-------|
| 1: Models + Loader | 1-3 | `models.py`, `loader.py`, `__init__.py`, example YAML | `workflow.yaml.j2` | `test_workflow_models.py`, `test_workflow_loader.py` |
| 2: Executor + Engine | 4-5 | `executor.py` | `__init__.py` | `test_workflow_executor.py`, `test_workflow_engine.py` |
| 3: API + CLI | 6-8, 11 | `workflows.py` (route) | `main.py`, `run.py`, `test_cli_run.py` | `test_workflow_api.py`, `test_cli_run_workflow.py` |
| 4: Dashboard | 9-10 | `dashboard.py` | `main.py` | `test_dashboard_api.py` |

**Total:** 11 tasks, 14 new files, 4 modified files, 8 new test files
