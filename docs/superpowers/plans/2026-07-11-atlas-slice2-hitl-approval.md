# HITL Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable human-approval step type (`StepType.APPROVAL`) to astromesh workflows — the run suspends, exposes a pending-approvals queue, and continues or diverts when a human approves/rejects — reusing the existing async-durable machinery.

**Architecture:** An APPROVAL step is a specialized WAIT. The executor emits `SUSPENDED` with approval metadata; the engine checkpoints it into the `WorkflowRunStore` with a `pending_approval` blob; `approve`/`reject` are a thin façade over the durable resume path that inject a decision record into the run context and then continue (approve), divert to `on_reject` (reject with handler), or terminate as `rejected`. Timeout is handled by the existing sweep, which redirects expired approvals through the same reject path. astromesh is **record-only**: it records who-must-approve and who-approved, but never authenticates/authorizes — that stays with the calling app.

**Tech Stack:** Python 3, `uv`, dataclasses, FastAPI, aiosqlite, pytest (async), Jinja2 (switch conditions).

## Global Constraints

- Python package manager is `uv`. Run tests with `uv run pytest`.
- CI runs **all three** and every one must be green before a task is done: `uv run pytest`, `uv run ruff check`, `uv run mypy src/`. (mypy is part of CI — do not skip it.)
- Run status is a plain `str` on `WorkflowRun` (existing convention: `"running"`, `"suspended"`, `"completed"`, `"failed"`, `"expired"`). The new terminal status is the string `"rejected"` — **do not** introduce a status enum.
- `approver` in any request body is **recorded, not verified**. Never add auth/identity checks.
- The workflows router has `prefix="/workflows"` and is mounted under `/v1`, so full paths are `/v1/workflows/...`. New routes that use a fixed first segment (`/approvals`, `/runs/...`) MUST be declared **before** the `/{name}` catch-all route in `astromesh/api/routes/workflows.py`.
- Decision records are injected as the approval step's output under `context["steps"][<step_name>] = {"output": <decision>}` — consistent with how `resume()` injects a wait payload and how switch conditions read `steps['<name>'].output.<field>`.
- Timestamps that the engine persists in the decision path are **passed in** by the caller/sweep (`decided_at`), never generated inside `_drive`/`_decide` — this preserves durable reproducibility. Endpoints and the sweep stamp `datetime.now(UTC).isoformat()`.

---

### Task 1: Models + loader — `APPROVAL` step type and `pending_approval` field

**Files:**
- Modify: `astromesh/workflow/models.py` (`StepType`, `StepSpec`, `WorkflowRun`)
- Modify: `astromesh/workflow/loader.py:_parse_step`
- Test: `tests/test_workflow_approval_models.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `StepType.APPROVAL` (value `"approval"`).
  - `StepSpec.approval: dict | None` — counted in the exactly-one-step-type check alongside `agent`/`tool`/`switch`/`wait`. `step_type` returns `StepType.APPROVAL` when set.
  - `WorkflowRun.pending_approval: dict | None = None` — carries `{"step_name", "approver", "prompt"}` while suspended at an approval.
  - Loader maps YAML `approval:` → `StepSpec.approval`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_approval_models.py
import pytest

from astromesh.workflow.models import StepSpec, StepType, WorkflowRun


def test_approval_step_type():
    step = StepSpec(name="ap", approval={"approver": "role:mgr", "prompt": "ok?"})
    assert step.step_type == StepType.APPROVAL
    assert StepType.APPROVAL.value == "approval"


def test_approval_counts_in_mutual_exclusion():
    # two step types → error that mentions approval
    with pytest.raises(ValueError, match="approval"):
        StepSpec(name="bad", tool="t", approval={"approver": "x"})
    # zero step types → error
    with pytest.raises(ValueError):
        StepSpec(name="empty")


def test_workflow_run_pending_approval_defaults_none():
    run = WorkflowRun(run_id="r1", workflow_name="wf", status="running", current_index=0)
    assert run.pending_approval is None


def test_loader_parses_approval_step():
    from pathlib import Path
    import tempfile
    from astromesh.workflow.loader import WorkflowLoader

    yaml_text = (
        "kind: Workflow\n"
        "metadata:\n  name: wf\n"
        "spec:\n  steps:\n"
        "    - name: aprobar\n"
        "      approval:\n        approver: role:finance_manager\n        prompt: Aprobar?\n"
        "        on_reject: avisar\n"
        "    - name: avisar\n      tool: notify\n"
    )
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.workflow.yaml"
        p.write_text(yaml_text)
        wf = WorkflowLoader(d).load_file(p)
    step = wf.get_step("aprobar")
    assert step.approval == {"approver": "role:finance_manager", "prompt": "Aprobar?", "on_reject": "avisar"}
    assert step.step_type == StepType.APPROVAL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_approval_models.py -v`
Expected: FAIL — `AttributeError: APPROVAL` / `TypeError: unexpected keyword argument 'approval'`.

- [ ] **Step 3: Write minimal implementation**

In `astromesh/workflow/models.py`, add the enum member:

```python
class StepType(str, Enum):
    AGENT = "agent"
    TOOL = "tool"
    SWITCH = "switch"
    WAIT = "wait"
    APPROVAL = "approval"
```

Add the `approval` field to `StepSpec` (right after `wait`):

```python
    wait: dict | None = None
    approval: dict | None = None
```

Update the mutual-exclusion count and `step_type` in `StepSpec`:

```python
        type_count = sum(
            1 for x in [self.agent, self.tool, self.switch, self.wait, self.approval]
            if x is not None
        )
        if type_count != 1:
            raise ValueError(
                f"Step '{self.name}' must have exactly one of: agent, tool, switch, wait, "
                f"approval (got {type_count})"
            )
```

```python
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
        return StepType.SWITCH
```

Add the field to `WorkflowRun` (after `error`):

```python
    error: str | None = None
    pending_approval: dict | None = None
```

In `astromesh/workflow/loader.py`, add to the `StepSpec(...)` call in `_parse_step`:

```python
            wait=raw.get("wait"),
            approval=raw.get("approval"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_approval_models.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full gate**

Run: `uv run pytest tests/test_workflow_models.py tests/test_workflow_loader.py -q && uv run ruff check && uv run mypy src/`
Expected: PASS (no regressions in existing model/loader tests; mypy clean).

- [ ] **Step 6: Commit**

```bash
git add astromesh/workflow/models.py astromesh/workflow/loader.py tests/test_workflow_approval_models.py
git commit -m "feat(workflow): APPROVAL step type + pending_approval run field + loader parse"
```

---

### Task 2: Executor — `_run_approval`

**Files:**
- Modify: `astromesh/workflow/executor.py` (`_dispatch`, new `_run_approval`)
- Test: `tests/test_workflow_approval_executor.py` (create)

**Interfaces:**
- Consumes: `StepType.APPROVAL` (Task 1).
- Produces: an APPROVAL step executes to `StepResult(status=SUSPENDED, output={...})` where output contains `resume_key`, `timeout_seconds`, `approver`, `prompt`, `on_reject`, and `pending_approval={"step_name","approver","prompt"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_approval_executor.py
from astromesh.workflow.executor import StepExecutor
from astromesh.workflow.models import StepSpec, StepStatus


async def test_approval_step_suspends_with_metadata():
    ex = StepExecutor(runtime=None, tool_registry=None)
    step = StepSpec(name="aprobar", approval={
        "approver": "role:finance_manager", "prompt": "Aprobar orden?",
        "on_reject": "avisar", "timeout_seconds": 3600})
    result = await ex.execute_step(step, context={})
    assert result.status == StepStatus.SUSPENDED
    out = result.output
    assert out["approver"] == "role:finance_manager"
    assert out["prompt"] == "Aprobar orden?"
    assert out["on_reject"] == "avisar"
    assert out["timeout_seconds"] == 3600
    assert out["pending_approval"] == {
        "step_name": "aprobar", "approver": "role:finance_manager", "prompt": "Aprobar orden?"}


async def test_approval_without_optional_fields():
    ex = StepExecutor(runtime=None, tool_registry=None)
    step = StepSpec(name="ap", approval={"approver": "u:jc"})
    result = await ex.execute_step(step, context={})
    assert result.status == StepStatus.SUSPENDED
    assert result.output["timeout_seconds"] is None
    assert result.output["on_reject"] is None
    assert result.output["pending_approval"]["approver"] == "u:jc"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_approval_executor.py -v`
Expected: FAIL — approval dispatched to the `raise ValueError("Unknown step type")` branch.

- [ ] **Step 3: Write minimal implementation**

In `astromesh/workflow/executor.py`, add a branch in `_dispatch` (after the WAIT branch):

```python
        elif step.step_type == StepType.WAIT:
            return self._run_wait(step)
        elif step.step_type == StepType.APPROVAL:
            return self._run_approval(step)
        raise ValueError(f"Unknown step type for step '{step.name}'")
```

Add the method (next to `_run_wait`):

```python
    def _run_approval(self, step: StepSpec) -> StepResult:
        ap = step.approval or {}
        return StepResult(
            name=step.name,
            status=StepStatus.SUSPENDED,
            output={
                "resume_key": ap.get("resume_key"),
                "timeout_seconds": ap.get("timeout_seconds"),
                "approver": ap.get("approver"),
                "prompt": ap.get("prompt"),
                "on_reject": ap.get("on_reject"),
                "pending_approval": {
                    "step_name": step.name,
                    "approver": ap.get("approver"),
                    "prompt": ap.get("prompt"),
                },
            },
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_approval_executor.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full gate**

Run: `uv run pytest tests/test_workflow_executor.py tests/test_workflow_wait_loader_exec.py -q && uv run ruff check && uv run mypy src/`
Expected: PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add astromesh/workflow/executor.py tests/test_workflow_approval_executor.py
git commit -m "feat(workflow): executor dispatches APPROVAL to SUSPENDED with approval metadata"
```

---

### Task 3: Store — persist `pending_approval`

**Files:**
- Modify: `astromesh/workflow/store.py` (`SqliteRunStore._COLS`, `initialize`, `_row`, `_from_row`)
- Test: `tests/test_workflow_run_store.py` (append)

**Interfaces:**
- Consumes: `WorkflowRun.pending_approval` (Task 1).
- Produces: both `InMemoryRunStore` and `SqliteRunStore` round-trip `pending_approval` through create/save/load/list_by_status. (InMemory already works via deep-copy; Sqlite needs a JSON column.)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_run_store.py  (append these)
import tempfile
from pathlib import Path

import pytest

from astromesh.workflow.models import WorkflowRun
from astromesh.workflow.store import InMemoryRunStore, SqliteRunStore


def _run_with_approval():
    return WorkflowRun(
        run_id="rap", workflow_name="wf", status="suspended", current_index=2,
        pending_approval={"step_name": "aprobar", "approver": "role:mgr", "prompt": "ok?"})


async def test_inmemory_roundtrips_pending_approval():
    store = InMemoryRunStore()
    await store.create(_run_with_approval())
    loaded = await store.load("rap")
    assert loaded.pending_approval == {"step_name": "aprobar", "approver": "role:mgr", "prompt": "ok?"}


async def test_sqlite_roundtrips_pending_approval():
    with tempfile.TemporaryDirectory() as d:
        store = SqliteRunStore(str(Path(d) / "runs.db"))
        await store.initialize()
        await store.create(_run_with_approval())
        loaded = await store.load("rap")
        assert loaded.pending_approval == {
            "step_name": "aprobar", "approver": "role:mgr", "prompt": "ok?"}
        # None round-trips too
        await store.save(WorkflowRun(run_id="r2", workflow_name="wf", status="running", current_index=0))
        r2 = await store.load("r2")
        assert r2.pending_approval is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_run_store.py -k pending_approval -v`
Expected: FAIL — `test_sqlite_roundtrips_pending_approval` fails (Sqlite drops the field → `None`); InMemory passes.

- [ ] **Step 3: Write minimal implementation**

In `astromesh/workflow/store.py`, extend `SqliteRunStore`:

```python
    _COLS = ("run_id", "workflow_name", "status", "current_index", "context",
             "resume_key", "created_at", "updated_at", "expires_at", "error",
             "pending_approval")
```

Add the column to `CREATE TABLE` in `initialize`:

```python
            "CREATE TABLE IF NOT EXISTS workflow_runs ("
            "run_id TEXT PRIMARY KEY, workflow_name TEXT, status TEXT, current_index INTEGER, "
            "context TEXT, resume_key TEXT, created_at TEXT, updated_at TEXT, "
            "expires_at TEXT, error TEXT, pending_approval TEXT)"
```

Extend `_row` (append the JSON-encoded field, keeping column order):

```python
    def _row(self, run: WorkflowRun) -> tuple:
        return (run.run_id, run.workflow_name, run.status, run.current_index,
                json.dumps(run.context), run.resume_key, run.created_at,
                run.updated_at, run.expires_at, run.error,
                json.dumps(run.pending_approval))
```

Extend `_from_row` (read index 10):

```python
    def _from_row(self, row) -> WorkflowRun:
        return WorkflowRun(
            run_id=row[0], workflow_name=row[1], status=row[2], current_index=row[3],
            context=json.loads(row[4]) if row[4] else {}, resume_key=row[5],
            created_at=row[6], updated_at=row[7], expires_at=row[8], error=row[9],
            pending_approval=json.loads(row[10]) if row[10] else None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_run_store.py -k pending_approval -v`
Expected: PASS (2 new tests).

- [ ] **Step 5: Run the full gate**

Run: `uv run pytest tests/test_workflow_run_store.py -q && uv run ruff check && uv run mypy src/`
Expected: PASS (existing store tests unaffected — new column has a default and existing rows read `None`).

- [ ] **Step 6: Commit**

```bash
git add astromesh/workflow/store.py tests/test_workflow_run_store.py
git commit -m "feat(workflow): SqliteRunStore persists pending_approval (JSON column)"
```

---

### Task 4: Engine — capture `pending_approval` on suspend

**Files:**
- Modify: `astromesh/workflow/__init__.py` (`_drive`, both SUSPENDED blocks)
- Test: `tests/test_workflow_approval_engine.py` (create)

**Interfaces:**
- Consumes: executor approval output (Task 2), store persistence (Task 3).
- Produces: after `run()` hits an APPROVAL step, the persisted `WorkflowRun` has `status="suspended"`, `current_index` pointing past the approval, and `pending_approval` populated from the step output.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_approval_engine.py
from astromesh.workflow.models import StepSpec, StepStatus, WorkflowSpec
from astromesh.workflow.store import InMemoryRunStore


class _ApprovalStubExecutor:
    """Delegates wait/approval/switch to the real executor; fixed output otherwise."""
    def __init__(self):
        from astromesh.workflow.executor import StepExecutor
        self._real = StepExecutor(runtime=None, tool_registry=None)

    async def execute_step(self, step, context):
        from astromesh.workflow.models import StepResult
        if step.step_type.value in ("wait", "approval", "switch"):
            return await self._real.execute_step(step, context)
        return StepResult(name=step.name, status=StepStatus.SUCCESS, output={"ok": step.name})


def _engine(steps, store):
    from astromesh.workflow import WorkflowEngine
    eng = WorkflowEngine(workflows_dir="", runtime=None, tool_registry=None, store=store)
    eng._workflows = {"wf": WorkflowSpec(name="wf", steps=steps)}
    eng._executor = _ApprovalStubExecutor()
    return eng


async def test_run_suspends_at_approval_with_pending_approval():
    store = InMemoryRunStore()
    eng = _engine(
        [StepSpec(name="a", tool="t"),
         StepSpec(name="aprobar", approval={"approver": "role:mgr", "prompt": "ok?"}),
         StepSpec(name="b", tool="t")],
        store)
    result = await eng.run("wf", trigger={})
    assert result.status == "suspended"
    saved = await store.load(result.run_id)
    assert saved.status == "suspended"
    assert saved.current_index == 2  # past the approval (index of "b")
    assert saved.pending_approval == {"step_name": "aprobar", "approver": "role:mgr", "prompt": "ok?"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_approval_engine.py::test_run_suspends_at_approval_with_pending_approval -v`
Expected: FAIL — `saved.pending_approval is None` (engine doesn't capture it yet).

- [ ] **Step 3: Write minimal implementation**

In `astromesh/workflow/__init__.py`, in the **main** SUSPENDED block inside `_drive`, add the `pending_approval` capture right after setting `resume_key`:

```python
                if result.status == WfStepStatus.SUSPENDED:
                    tracing.finish_span(step_span)
                    run.status = "suspended"
                    run.current_index = i + 1  # resume after the wait
                    run.resume_key = (result.output or {}).get("resume_key")
                    run.pending_approval = (result.output or {}).get("pending_approval")
                    timeout = (result.output or {}).get("timeout_seconds")
```

And in the **switch-goto** SUSPENDED sub-block, the mirror line right after its `resume_key`:

```python
                        if goto_result.status == WfStepStatus.SUSPENDED:
                            tracing.finish_span(goto_span)
                            run.status = "suspended"
                            run.current_index = step_index[goto_step.name] + 1  # resume after the wait
                            run.resume_key = (goto_result.output or {}).get("resume_key")
                            run.pending_approval = (goto_result.output or {}).get("pending_approval")
                            timeout = (goto_result.output or {}).get("timeout_seconds")
```

(Plain WAIT steps have no `pending_approval` key in their output, so this sets `None` for them — no behavior change for waits.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_approval_engine.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full gate**

Run: `uv run pytest tests/test_workflow_durable_engine.py tests/test_workflow_resume.py -q && uv run ruff check && uv run mypy src/`
Expected: PASS (wait/resume behavior unchanged — `pending_approval` is `None` for waits).

- [ ] **Step 6: Commit**

```bash
git add astromesh/workflow/__init__.py tests/test_workflow_approval_engine.py
git commit -m "feat(workflow): engine captures pending_approval when suspending at an APPROVAL step"
```

---

### Task 5: Engine — `approve` / `reject` / `_decide` / `list_pending_approvals`

**Files:**
- Modify: `astromesh/workflow/__init__.py` (add methods)
- Test: `tests/test_workflow_approval_engine.py` (append)

**Interfaces:**
- Consumes: pending-approval capture (Task 4), the existing `_drive` and `_store`.
- Produces:
  - `async approve(run_id, approver, comment, decided_at) -> WorkflowRunResult`
  - `async reject(run_id, approver, comment, decided_at) -> WorkflowRunResult`
  - `async list_pending_approvals(approver: str | None = None) -> list[WorkflowRun]`
  - Both `approve`/`reject` inject `context["steps"][<approval_step>] = {"output": {"approved", "approver", "comment", "decided_at"}}`, clear `pending_approval`, then: approve → continue via `_drive`; reject with `on_reject` → jump to that step and `_drive`; reject without `on_reject` → status `"rejected"`.
  - Raise `ValueError` containing `"not found"` when the run is missing, and `ValueError` (without `"not found"`) when the run is not suspended-in-an-approval — matching the `resume()` error convention the API maps to 404/409.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_approval_engine.py  (append; reuses _engine / _ApprovalStubExecutor above)
import pytest

from astromesh.workflow.models import StepSpec
from astromesh.workflow.store import InMemoryRunStore


async def _suspend_at_approval(store, extra_steps=None, approval=None):
    approval = approval or {"approver": "role:mgr", "prompt": "ok?"}
    steps = [StepSpec(name="a", tool="t"),
             StepSpec(name="aprobar", approval=approval)] + (extra_steps or [StepSpec(name="b", tool="t")])
    eng = _engine(steps, store)
    r = await eng.run("wf", trigger={})
    return eng, r.run_id


async def test_approve_continues_and_records_decision():
    store = InMemoryRunStore()
    eng, run_id = await _suspend_at_approval(store)
    result = await eng.approve(run_id, approver="u:jc", comment="ok", decided_at="2026-07-11T10:00:00")
    assert result.status == "completed"
    saved = await store.load(run_id)
    decision = saved.context["steps"]["aprobar"]["output"]
    assert decision == {"approved": True, "approver": "u:jc", "comment": "ok",
                        "decided_at": "2026-07-11T10:00:00"}
    assert saved.pending_approval is None


async def test_reject_with_on_reject_jumps():
    store = InMemoryRunStore()
    eng, run_id = await _suspend_at_approval(
        store,
        extra_steps=[StepSpec(name="avisar", tool="t"), StepSpec(name="b", tool="t")],
        approval={"approver": "role:mgr", "prompt": "ok?", "on_reject": "avisar"})
    result = await eng.reject(run_id, approver="u:jc", comment="no", decided_at="2026-07-11T10:00:00")
    assert result.status == "completed"          # ran avisar → b
    saved = await store.load(run_id)
    assert saved.context["steps"]["aprobar"]["output"]["approved"] is False
    assert "avisar" in saved.context["steps"]     # the reject branch executed


async def test_reject_without_on_reject_terminates_rejected():
    store = InMemoryRunStore()
    eng, run_id = await _suspend_at_approval(store)
    result = await eng.reject(run_id, approver="u:jc", comment=None, decided_at="2026-07-11T10:00:00")
    assert result.status == "rejected"
    saved = await store.load(run_id)
    assert saved.status == "rejected"
    assert saved.pending_approval is None


async def test_switch_routes_on_decision():
    # approval → switch that goes to "aprobado" when approved, else default "rechazado"
    store = InMemoryRunStore()
    steps = [
        StepSpec(name="aprobar", approval={"approver": "role:mgr", "prompt": "ok?"}),
        StepSpec(name="ruta", switch=[
            {"when": "{{ steps['aprobar'].output.approved }}", "goto": "aprobado"},
            {"default": True, "goto": "rechazado"}]),
        StepSpec(name="aprobado", tool="t"),
        StepSpec(name="rechazado", tool="t"),
    ]
    eng = _engine(steps, store)
    run_id = (await eng.run("wf", trigger={})).run_id
    await eng.approve(run_id, approver="u:jc", comment=None, decided_at="2026-07-11T10:00:00")
    saved = await store.load(run_id)
    assert "aprobado" in saved.context["steps"]
    assert "rechazado" not in saved.context["steps"]


async def test_approve_unknown_run_raises_not_found():
    eng = _engine([StepSpec(name="a", tool="t")], InMemoryRunStore())
    with pytest.raises(ValueError, match="not found"):
        await eng.approve("nope", approver="u:jc", comment=None, decided_at="t")


async def test_approve_non_approval_run_raises():
    # a run that completed (not awaiting approval) → ValueError without "not found"
    store = InMemoryRunStore()
    eng = _engine([StepSpec(name="a", tool="t")], store)
    run_id = (await eng.run("wf", trigger={})).run_id
    with pytest.raises(ValueError) as exc:
        await eng.approve(run_id, approver="u:jc", comment=None, decided_at="t")
    assert "not found" not in str(exc.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_approval_engine.py -k "approve or reject or switch_routes" -v`
Expected: FAIL — `AttributeError: 'WorkflowEngine' object has no attribute 'approve'`.

- [ ] **Step 3: Write minimal implementation**

In `astromesh/workflow/__init__.py`, add these methods to `WorkflowEngine` (place them after `resume`):

```python
    async def list_pending_approvals(self, approver: str | None = None) -> list[WorkflowRun]:
        runs = [r for r in await self._store.list_by_status("suspended") if r.pending_approval]
        if approver is not None:
            runs = [r for r in runs if (r.pending_approval or {}).get("approver") == approver]
        return runs

    async def approve(self, run_id: str, approver: str, comment: str | None,
                      decided_at: str) -> WorkflowRunResult:
        return await self._decide(run_id, True, approver, comment, decided_at)

    async def reject(self, run_id: str, approver: str, comment: str | None,
                     decided_at: str) -> WorkflowRunResult:
        return await self._decide(run_id, False, approver, comment, decided_at)

    async def _decide(self, run_id: str, approved: bool, approver: str,
                      comment: str | None, decided_at: str) -> WorkflowRunResult:
        run = await self._store.load(run_id)
        if run is None:
            raise ValueError(f"Run '{run_id}' not found")
        if run.status != "suspended" or not run.pending_approval:
            raise ValueError(
                f"Run '{run_id}' is not awaiting approval (status={run.status})")

        wf = self._workflows.get(run.workflow_name)
        if not wf:
            raise ValueError(f"Workflow '{run.workflow_name}' not found")

        approval_idx = run.current_index - 1  # the APPROVAL step sits just before current_index
        step = wf.steps[approval_idx] if 0 <= approval_idx < len(wf.steps) else None
        decision = {"approved": approved, "approver": approver,
                    "comment": comment, "decided_at": decided_at}
        if step is not None:
            run.context["steps"][step.name] = {"output": decision}
        run.pending_approval = None

        if approved:
            run.status = "running"
            await self._store.save(run)
            return await self._drive(wf, run)

        # rejected
        on_reject = (step.approval or {}).get("on_reject") if step is not None else None
        step_index = {s.name: i for i, s in enumerate(wf.steps)}
        if on_reject and on_reject in step_index:
            run.status = "running"
            run.current_index = step_index[on_reject]
            await self._store.save(run)
            return await self._drive(wf, run)

        run.status = "rejected"
        run.updated_at = decided_at
        await self._store.save(run)
        return WorkflowRunResult(
            workflow_name=run.workflow_name, status="rejected", run_id=run.run_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_approval_engine.py -v`
Expected: PASS (all approval-engine tests).

- [ ] **Step 5: Run the full gate**

Run: `uv run pytest tests/test_workflow_durable_engine.py tests/test_workflow_resume.py -q && uv run ruff check && uv run mypy src/`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add astromesh/workflow/__init__.py tests/test_workflow_approval_engine.py
git commit -m "feat(workflow): approve/reject/list_pending_approvals + decision injection & on_reject routing"
```

---

### Task 6: Engine — sweep timeout redirects approvals to reject

**Files:**
- Modify: `astromesh/workflow/__init__.py` (`sweep_expired`)
- Test: `tests/test_workflow_approval_sweep.py` (create)

**Interfaces:**
- Consumes: `reject` (Task 5), `pending_approval` on the run (Task 4).
- Produces: `sweep_expired(now)` — for an expired suspended run that is a pending approval, calls `reject(run_id, approver="system:timeout", comment=None, decided_at=now)` (which routes to `on_reject` or terminates `rejected`); for an expired non-approval WAIT it keeps the current `expired` behavior; approvals without `expires_at` are untouched.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_approval_sweep.py
from astromesh.workflow.models import StepSpec, StepStatus, WorkflowSpec
from astromesh.workflow.store import InMemoryRunStore


class _ApprovalStubExecutor:
    def __init__(self):
        from astromesh.workflow.executor import StepExecutor
        self._real = StepExecutor(runtime=None, tool_registry=None)

    async def execute_step(self, step, context):
        from astromesh.workflow.models import StepResult
        if step.step_type.value in ("wait", "approval", "switch"):
            return await self._real.execute_step(step, context)
        return StepResult(name=step.name, status=StepStatus.SUCCESS, output={"ok": step.name})


def _engine(steps, store):
    from astromesh.workflow import WorkflowEngine
    eng = WorkflowEngine(workflows_dir="", runtime=None, tool_registry=None, store=store)
    eng._workflows = {"wf": WorkflowSpec(name="wf", steps=steps)}
    eng._executor = _ApprovalStubExecutor()
    return eng


async def test_expired_approval_without_on_reject_becomes_rejected():
    store = InMemoryRunStore()
    eng = _engine(
        [StepSpec(name="aprobar", approval={
            "approver": "role:mgr", "prompt": "ok?", "timeout_seconds": 1}),
         StepSpec(name="b", tool="t")],
        store)
    run_id = (await eng.run("wf", trigger={})).run_id
    # expires_at was set 1s out; sweep with a far-future "now"
    n = await eng.sweep_expired(now="2999-01-01T00:00:00")
    assert n == 1
    saved = await store.load(run_id)
    assert saved.status == "rejected"
    assert saved.context["steps"]["aprobar"]["output"]["approver"] == "system:timeout"
    assert saved.context["steps"]["aprobar"]["output"]["approved"] is False


async def test_expired_approval_with_on_reject_jumps():
    store = InMemoryRunStore()
    eng = _engine(
        [StepSpec(name="aprobar", approval={
            "approver": "role:mgr", "prompt": "ok?", "on_reject": "avisar", "timeout_seconds": 1}),
         StepSpec(name="avisar", tool="t")],
        store)
    run_id = (await eng.run("wf", trigger={})).run_id
    await eng.sweep_expired(now="2999-01-01T00:00:00")
    saved = await store.load(run_id)
    assert saved.status == "completed"          # ran avisar
    assert "avisar" in saved.context["steps"]


async def test_approval_without_timeout_not_swept():
    store = InMemoryRunStore()
    eng = _engine(
        [StepSpec(name="aprobar", approval={"approver": "role:mgr", "prompt": "ok?"}),
         StepSpec(name="b", tool="t")],
        store)
    run_id = (await eng.run("wf", trigger={})).run_id
    n = await eng.sweep_expired(now="2999-01-01T00:00:00")
    assert n == 0
    assert (await store.load(run_id)).status == "suspended"


async def test_expired_plain_wait_still_expires():
    store = InMemoryRunStore()
    eng = _engine(
        [StepSpec(name="w", wait={"resume_key": "k", "timeout_seconds": 1}),
         StepSpec(name="b", tool="t")],
        store)
    run_id = (await eng.run("wf", trigger={})).run_id
    await eng.sweep_expired(now="2999-01-01T00:00:00")
    assert (await store.load(run_id)).status == "expired"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_approval_sweep.py -v`
Expected: FAIL — expired approvals get `status="expired"` instead of `rejected`/`completed`.

- [ ] **Step 3: Write minimal implementation**

In `astromesh/workflow/__init__.py`, replace `sweep_expired`:

```python
    async def sweep_expired(self, now: str) -> int:
        n = 0
        for run in await self._store.list_by_status("suspended"):
            if not (run.expires_at and run.expires_at < now):
                continue
            if run.pending_approval:
                await self.reject(run.run_id, approver="system:timeout",
                                  comment=None, decided_at=now)
            else:
                run.status = "expired"
                run.error = "wait timed out"
                await self._store.save(run)
            n += 1
        return n
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_approval_sweep.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full gate**

Run: `uv run pytest tests/test_workflow_sweeps.py -q && uv run ruff check && uv run mypy src/`
Expected: PASS (non-approval sweep behavior unchanged).

- [ ] **Step 6: Commit**

```bash
git add astromesh/workflow/__init__.py tests/test_workflow_approval_sweep.py
git commit -m "feat(workflow): sweep redirects expired approvals through the reject path (system:timeout)"
```

---

### Task 7: API — approvals queue + approve/reject endpoints

**Files:**
- Modify: `astromesh/api/routes/workflows.py` (new request model + 3 routes, declared before `/{name}`)
- Test: `tests/test_workflow_approval_api.py` (create)

**Interfaces:**
- Consumes: `list_pending_approvals`, `approve`, `reject` (Task 5).
- Produces:
  - `GET /v1/workflows/approvals[?approver=...]` → `{"approvals": [{run_id, workflow_name, step_name, approver, prompt, created_at, expires_at}, ...]}`
  - `POST /v1/workflows/runs/{run_id}/approve` body `{approver, comment?}` → `{run_id, status}` (404/409/503 mapping)
  - `POST /v1/workflows/runs/{run_id}/reject` body `{approver, comment?}` → `{run_id, status}`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_approval_api.py
import pytest

from astromesh.api.routes import workflows as wf_route
from astromesh.workflow.models import StepSpec, StepStatus, WorkflowSpec
from astromesh.workflow.store import InMemoryRunStore


class _ApprovalStubExecutor:
    def __init__(self):
        from astromesh.workflow.executor import StepExecutor
        self._real = StepExecutor(runtime=None, tool_registry=None)

    async def execute_step(self, step, context):
        from astromesh.workflow.models import StepResult
        if step.step_type.value in ("wait", "approval", "switch"):
            return await self._real.execute_step(step, context)
        return StepResult(name=step.name, status=StepStatus.SUCCESS, output={"ok": step.name})


@pytest.fixture
def wired():
    from astromesh.workflow import WorkflowEngine
    eng = WorkflowEngine(workflows_dir="", runtime=None, tool_registry=None, store=InMemoryRunStore())
    eng._workflows = {"wf": WorkflowSpec(name="wf", steps=[
        StepSpec(name="aprobar", approval={"approver": "role:finance_manager", "prompt": "Aprobar?"}),
        StepSpec(name="b", tool="t")])}
    eng._executor = _ApprovalStubExecutor()
    wf_route.set_workflow_engine(eng)
    return eng


async def test_queue_lists_pending_approval(client, wired):
    r = await client.post("/v1/workflows/wf/run", json={"trigger": {}})
    run_id = r.json()["run_id"]
    q = await client.get("/v1/workflows/approvals")
    assert q.status_code == 200
    items = q.json()["approvals"]
    assert len(items) == 1
    assert items[0]["run_id"] == run_id
    assert items[0]["step_name"] == "aprobar"
    assert items[0]["approver"] == "role:finance_manager"
    assert items[0]["prompt"] == "Aprobar?"


async def test_queue_filters_by_approver(client, wired):
    await client.post("/v1/workflows/wf/run", json={"trigger": {}})
    hit = await client.get("/v1/workflows/approvals", params={"approver": "role:finance_manager"})
    miss = await client.get("/v1/workflows/approvals", params={"approver": "role:other"})
    assert len(hit.json()["approvals"]) == 1
    assert len(miss.json()["approvals"]) == 0


async def test_approve_endpoint(client, wired):
    run_id = (await client.post("/v1/workflows/wf/run", json={"trigger": {}})).json()["run_id"]
    a = await client.post(f"/v1/workflows/runs/{run_id}/approve",
                          json={"approver": "u:jc", "comment": "ok"})
    assert a.status_code == 200 and a.json()["status"] == "completed"


async def test_reject_endpoint(client, wired):
    run_id = (await client.post("/v1/workflows/wf/run", json={"trigger": {}})).json()["run_id"]
    a = await client.post(f"/v1/workflows/runs/{run_id}/reject", json={"approver": "u:jc"})
    assert a.status_code == 200 and a.json()["status"] == "rejected"


async def test_approve_unknown_run_404(client, wired):
    a = await client.post("/v1/workflows/runs/nope/approve", json={"approver": "u:jc"})
    assert a.status_code == 404


async def test_double_approve_409(client, wired):
    run_id = (await client.post("/v1/workflows/wf/run", json={"trigger": {}})).json()["run_id"]
    await client.post(f"/v1/workflows/runs/{run_id}/approve", json={"approver": "u:jc"})
    again = await client.post(f"/v1/workflows/runs/{run_id}/approve", json={"approver": "u:jc"})
    assert again.status_code == 409
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_approval_api.py -v`
Expected: FAIL — routes return 404 (not defined) / `approvals` treated as a workflow name by `/{name}`.

- [ ] **Step 3: Write minimal implementation**

In `astromesh/api/routes/workflows.py`, add the import at the top:

```python
from datetime import UTC, datetime
```

Add the request model next to `ResumeRequest`:

```python
class DecisionRequest(BaseModel):
    approver: str
    comment: str | None = None
```

Add the three routes **before** the `@router.get("/{name}")` route (e.g. right after `resume_run`):

```python
@router.get("/approvals")
async def list_approvals(approver: str | None = None):
    if not _engine:
        raise HTTPException(status_code=503, detail="Workflow engine not initialized")
    runs = await _engine.list_pending_approvals(approver)
    return {
        "approvals": [
            {
                "run_id": r.run_id,
                "workflow_name": r.workflow_name,
                "step_name": (r.pending_approval or {}).get("step_name"),
                "approver": (r.pending_approval or {}).get("approver"),
                "prompt": (r.pending_approval or {}).get("prompt"),
                "created_at": r.created_at,
                "expires_at": r.expires_at,
            }
            for r in runs
        ]
    }


async def _decide_endpoint(run_id: str, request: "DecisionRequest", approved: bool):
    if not _engine:
        raise HTTPException(status_code=503, detail="Workflow engine not initialized")
    decided_at = datetime.now(UTC).isoformat()
    fn = _engine.approve if approved else _engine.reject
    try:
        result = await fn(run_id, request.approver, request.comment, decided_at)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    return {"run_id": result.run_id, "status": result.status}


@router.post("/runs/{run_id}/approve")
async def approve_run(run_id: str, request: DecisionRequest):
    return await _decide_endpoint(run_id, request, approved=True)


@router.post("/runs/{run_id}/reject")
async def reject_run(run_id: str, request: DecisionRequest):
    return await _decide_endpoint(run_id, request, approved=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_approval_api.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full gate**

Run: `uv run pytest tests/test_workflow_api.py tests/test_workflow_durable_api.py -q && uv run ruff check && uv run mypy src/`
Expected: PASS (existing workflow API unaffected; `/approvals` and `/runs/...` resolve before `/{name}`).

- [ ] **Step 6: Commit**

```bash
git add astromesh/api/routes/workflows.py tests/test_workflow_approval_api.py
git commit -m "feat(api): approvals queue + approve/reject endpoints (record-only HITL)"
```

---

### Task 8: Full-suite gate + docs note

**Files:**
- Modify: `docs/superpowers/plans/2026-07-11-atlas-slice2-hitl-approval.md` (check boxes as executed — optional)

- [ ] **Step 1: Run the entire test suite + linters + types**

Run: `uv run pytest -q && uv run ruff check && uv run mypy src/`
Expected: all green. If any pre-existing unrelated failures appear, note them but do not fix out of scope.

- [ ] **Step 2: Sanity-check the end-to-end approval path manually (optional)**

Confirm the wiring reads correctly: `run()` → suspend at APPROVAL → `GET /v1/workflows/approvals` shows it → `POST .../approve` → `completed`. (This is covered by Task 7 tests; step is a final read-through, no code.)

- [ ] **Step 3: Commit any remaining checkbox updates**

```bash
git add -A && git commit -m "chore: HITL approval slice complete (Slice 2 parte 3)" || echo "nothing to commit"
```

---

## Self-Review

**Spec coverage:**
- `StepType.APPROVAL` + YAML shape → Task 1 (models) + Task 2 (executor) + Task 1 (loader parse). ✓
- Record-only (no authz) → enforced by design; `approver` only recorded (Tasks 5, 7). ✓
- `pending_approval` on run + queue → Task 1 (field), Task 3 (Sqlite persist), Task 4 (capture), Task 5 (`list_pending_approvals`), Task 7 (`GET /approvals`). ✓
- Decision injected into context, switch routes on it → Task 5 (`_decide` injection + `test_switch_routes_on_decision`). ✓
- Reject: `on_reject` jump vs terminal `rejected` → Task 5. ✓
- Timeout = auto-reject reusing reject path; no-timeout = never swept; plain wait still `expired` → Task 6. ✓
- API `GET /approvals`, `POST approve|reject`, 404/409/503 mapping, declared before `/{name}` → Task 7. ✓
- mypy in CI → every task's Step 5 runs `uv run mypy src/`. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. ✓

**Type consistency:** `pending_approval: dict | None` used consistently (models, store, engine, API); `approve`/`reject`/`_decide` signatures `(run_id, approver, comment, decided_at)` match across engine and API; decision dict keys `approved/approver/comment/decided_at` identical in Task 5 and Task 6 and asserted in Task 7. Status string `"rejected"` consistent throughout. ✓

**Out of scope (per spec):** identity/authz, cockpit UI, notifications, `PgRunStore`, multi-signature approvals. Not planned. ✓
