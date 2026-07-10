# Atlas Slice 2 (parte 2) — Ejecución durable de workflows · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un `Workflow` de astromesh pueda suspenderse en un step `wait` (esperando un evento externo) y resumir después desde un estado persistido, sobreviviendo a reinicios, sin romper el contrato síncrono actual.

**Architecture:** Un nuevo `StepType.WAIT` señala suspensión; un `WorkflowRunStore` durable persiste el estado de cada corrida con checkpoint por-step; `WorkflowEngine.run` se vuelve durable pero mantiene una **fachada síncrona** (corrida simple → resultado completo como hoy; corrida que suspende → `run_id`+`suspended`), y gana `resume(run_id, payload)`. Sweeps resuelven esperas vencidas (`expired`) y corridas huérfanas por crash (`failed`).

**Tech Stack:** Python 3.13, `uv`, FastAPI, `aiosqlite`, pytest + pytest-asyncio, ruff. Espeja `astromesh/memory/backends/sqlite_conv.py` (patrón DB) y los orchestrators de Optimus/Atlas (sweep de huérfanas).

## Global Constraints

- Repo de trabajo: **astromesh** (rama `feat/atlas-slice2-async-durable`). NO tocar `clarus-platform`.
- Verificación de cada tarea: `uv run pytest <archivo> -v` en verde **y** `uv run ruff check .` sin errores nuevos (hay errores ruff PRE-EXISTENTES no relacionados en `astromesh-adk/`, `astromesh-node/`, `astromesh-orbit/` — ignorarlos; solo los archivos tocados deben quedar limpios). Falla pre-existente conocida no relacionada: `tests/test_memory_factory.py::test_builds_redis_backend_lazily`.
- No romper el contrato síncrono: un workflow **sin** step `wait` debe seguir devolviendo su `WorkflowRunResult` completo por `POST /run` (más el nuevo campo `run_id`). Preservar la lógica actual de `on_error` (goto), `switch goto`, retry/timeout de steps.
- **Persistencia por-step (checkpoint):** el engine hace `store.save` después de cada step. Semántica at-least-once (un crash mid-step re-ejecuta ese step al resumir).
- Store pluggable espejando `astromesh/memory/backends/`. Este plan implementa `InMemoryRunStore` (engine + tests) y `SqliteRunStore` (durable, testeable offline). **`PgRunStore` queda como follow-up** (requiere un Postgres vivo para test significativo; sqlite prueba la durabilidad). Divergencia consciente del spec, documentada acá.
- Timestamps: los sweeps reciben `now` como parámetro (test lo inyecta). El engine usa `datetime.now(UTC)` real para `expires_at` (los tests de suspend no asertan su valor exacto).
- Nombres reales verificados: clase engine `WorkflowEngine` (`astromesh/workflow/__init__.py`); `StepExecutor` (`executor.py`); modelos en `models.py`; loader `WorkflowLoader` (`loader.py`); ruta `astromesh/api/routes/workflows.py` (router `prefix="/workflows"`); wiring por `set_workflow_engine(engine)`.

## File Structure

- Modify `astromesh/workflow/models.py` — `StepType.WAIT`, `StepStatus.SUSPENDED`, `StepSpec.wait`, `WorkflowRunResult.run_id`, nuevo `WorkflowRun`.
- Modify `astromesh/workflow/loader.py` — `_parse_step` lee `wait`.
- Modify `astromesh/workflow/executor.py` — `_dispatch`/`_run_wait` para WAIT.
- Create `astromesh/workflow/store.py` — `WorkflowRun` (re-export), `WorkflowRunStore` (ABC), `InMemoryRunStore`, `SqliteRunStore`.
- Modify `astromesh/workflow/__init__.py` — `WorkflowEngine` durable: `__init__(store=...)`, `run` con checkpoint+suspend, `resume`, `sweep_expired`, `mark_orphaned_failed`, wiring del store al bootstrap.
- Modify `astromesh/api/routes/workflows.py` — `POST /run` (fachada), `GET /runs/{id}`, `POST /runs/{id}/resume`.
- Create tests: `tests/test_workflow_wait_models.py`, `tests/test_workflow_wait_loader_exec.py`, `tests/test_workflow_run_store.py`, `tests/test_workflow_durable_engine.py`, `tests/test_workflow_resume.py`, `tests/test_workflow_sweeps.py`, `tests/test_workflow_durable_api.py`.

---

### Task 1: Modelos — WAIT, SUSPENDED, StepSpec.wait, WorkflowRun

**Files:**
- Modify: `astromesh/workflow/models.py`
- Test: `tests/test_workflow_wait_models.py`

**Interfaces:**
- Produces: `StepType.WAIT`; `StepStatus.SUSPENDED`; `StepSpec.wait: dict | None`; `StepSpec.step_type` devuelve `WAIT` cuando hay `wait`; `WorkflowRunResult.run_id: str | None`; `WorkflowRun` dataclass (`run_id, workflow_name, status, current_index, context, resume_key, created_at, updated_at, expires_at, error`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_wait_models.py
import pytest

from astromesh.workflow.models import (
    StepSpec, StepStatus, StepType, WorkflowRun, WorkflowRunResult,
)


def test_wait_step_type():
    s = StepSpec(name="w", wait={"resume_key": "k", "timeout_seconds": 60})
    assert s.step_type == StepType.WAIT


def test_exactly_one_step_type_still_enforced():
    with pytest.raises(ValueError):
        StepSpec(name="bad", agent="a", wait={"resume_key": "k"})
    with pytest.raises(ValueError):
        StepSpec(name="none")


def test_suspended_status_exists():
    assert StepStatus.SUSPENDED.value == "suspended"


def test_run_result_has_run_id():
    r = WorkflowRunResult(workflow_name="w", status="suspended", run_id="r1")
    assert r.run_id == "r1"


def test_workflow_run_dataclass():
    run = WorkflowRun(run_id="r1", workflow_name="w", status="running",
                      current_index=0, context={"trigger": {}, "steps": {}})
    assert run.status == "running" and run.resume_key is None and run.error is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_wait_models.py -v`
Expected: FAIL — `AttributeError`/`TypeError` (WAIT/SUSPENDED/wait/run_id/WorkflowRun no existen).

- [ ] **Step 3: Write minimal implementation**

En `astromesh/workflow/models.py`:

(a) `StepType`: agregar `WAIT = "wait"`.
(b) `StepStatus`: agregar `SUSPENDED = "suspended"`.
(c) `StepSpec`: agregar el campo `wait: list[dict] | dict | None = None` (declararlo junto a `switch`). En `__post_init__`, incluir `wait` en el conteo de tipos:
```python
        type_count = sum(
            1 for x in [self.agent, self.tool, self.switch, self.wait] if x is not None
        )
```
En `step_type`, antes del `return StepType.SWITCH` final:
```python
        if self.wait is not None:
            return StepType.WAIT
```
(d) `WorkflowRunResult`: agregar `run_id: str | None = None` (al final de los campos).
(e) Al final del archivo, agregar:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_wait_models.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix astromesh/workflow/models.py tests/test_workflow_wait_models.py
git add astromesh/workflow/models.py tests/test_workflow_wait_models.py
git commit -m "feat(workflow): modelos para wait durable (WAIT/SUSPENDED/StepSpec.wait/WorkflowRun)"
```

---

### Task 2: Loader + Executor — cargar y despachar el step `wait`

**Files:**
- Modify: `astromesh/workflow/loader.py`
- Modify: `astromesh/workflow/executor.py`
- Test: `tests/test_workflow_wait_loader_exec.py`

**Interfaces:**
- Consumes: `StepType.WAIT`, `StepStatus.SUSPENDED` (Task 1).
- Produces: `WorkflowLoader.load_file` parsea `wait` en el `StepSpec`; `StepExecutor.execute_step` sobre un step wait devuelve `StepResult(status=SUSPENDED, output={"resume_key", "timeout_seconds"})`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_wait_loader_exec.py
from pathlib import Path

from astromesh.workflow.executor import StepExecutor
from astromesh.workflow.loader import WorkflowLoader
from astromesh.workflow.models import StepSpec, StepStatus, StepType

WF = """
apiVersion: astromesh/v1
kind: Workflow
metadata: {name: pago}
spec:
  steps:
    - name: esperar-pago
      wait: {resume_key: payment.confirmed, timeout_seconds: 60}
"""


def test_loader_parses_wait(tmp_path):
    p = tmp_path / "pago.workflow.yaml"
    p.write_text(WF)
    wf = WorkflowLoader(str(tmp_path)).load_file(p)
    step = wf.steps[0]
    assert step.step_type == StepType.WAIT
    assert step.wait["resume_key"] == "payment.confirmed"


async def test_executor_wait_suspends():
    execu = StepExecutor(runtime=None, tool_registry=None)
    step = StepSpec(name="w", wait={"resume_key": "k", "timeout_seconds": 30})
    result = await execu.execute_step(step, context={})
    assert result.status == StepStatus.SUSPENDED
    assert result.output == {"resume_key": "k", "timeout_seconds": 30}
```

(Si los tests `async def` necesitan marcador, seguí el patrón de los `tests/` existentes — `pytest-asyncio` está en modo auto en este repo.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_wait_loader_exec.py -v`
Expected: FAIL — el loader no pasa `wait`; el executor tira `ValueError: Unknown step type`.

- [ ] **Step 3: Write minimal implementation**

(a) `astromesh/workflow/loader.py`, en `_parse_step`, agregar al `StepSpec(...)` construido:
```python
            wait=raw.get("wait"),
```
(b) `astromesh/workflow/executor.py`:
- Importar `StepType` ya está. En `_dispatch`, agregar antes del `raise`:
```python
        elif step.step_type == StepType.WAIT:
            return self._run_wait(step)
```
- Agregar el método:
```python
    def _run_wait(self, step: StepSpec) -> StepResult:
        wait = step.wait or {}
        return StepResult(
            name=step.name,
            status=StepStatus.SUSPENDED,
            output={"resume_key": wait.get("resume_key"),
                    "timeout_seconds": wait.get("timeout_seconds")},
        )
```
(`_run_wait` es sync; `_dispatch` lo retorna directamente — no es `await` porque no hace I/O. Confirmar que `execute_step` maneja el resultado: `_dispatch` es `async` y `_run_wait` devuelve un `StepResult`, así que `return self._run_wait(step)` dentro de un método `async` está bien.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_wait_loader_exec.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix astromesh/workflow/loader.py astromesh/workflow/executor.py tests/test_workflow_wait_loader_exec.py
git add astromesh/workflow/loader.py astromesh/workflow/executor.py tests/test_workflow_wait_loader_exec.py
git commit -m "feat(workflow): loader parsea wait + executor lo despacha a SUSPENDED"
```

---

### Task 3: `WorkflowRunStore` (ABC) + `InMemoryRunStore`

**Files:**
- Create: `astromesh/workflow/store.py`
- Test: `tests/test_workflow_run_store.py`

**Interfaces:**
- Consumes: `WorkflowRun` (Task 1).
- Produces: `WorkflowRunStore` (ABC con `create/load/save/list_by_status`); `InMemoryRunStore`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_run_store.py
from astromesh.workflow.models import WorkflowRun
from astromesh.workflow.store import InMemoryRunStore


def _run(run_id, status="running"):
    return WorkflowRun(run_id=run_id, workflow_name="w", status=status,
                       current_index=0, context={"steps": {}})


async def test_create_load_roundtrip():
    store = InMemoryRunStore()
    await store.create(_run("r1"))
    loaded = await store.load("r1")
    assert loaded is not None and loaded.run_id == "r1"
    assert await store.load("nope") is None


async def test_save_updates():
    store = InMemoryRunStore()
    await store.create(_run("r1"))
    run = await store.load("r1")
    run.status = "suspended"
    run.current_index = 3
    await store.save(run)
    again = await store.load("r1")
    assert again.status == "suspended" and again.current_index == 3


async def test_list_by_status():
    store = InMemoryRunStore()
    await store.create(_run("r1", "running"))
    await store.create(_run("r2", "suspended"))
    await store.create(_run("r3", "running"))
    running = await store.list_by_status("running")
    assert {r.run_id for r in running} == {"r1", "r3"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_run_store.py -v`
Expected: FAIL — `ModuleNotFoundError: astromesh.workflow.store`.

- [ ] **Step 3: Write minimal implementation**

```python
# astromesh/workflow/store.py
from __future__ import annotations

import copy
from abc import ABC, abstractmethod

from astromesh.workflow.models import WorkflowRun


class WorkflowRunStore(ABC):
    @abstractmethod
    async def create(self, run: WorkflowRun) -> None: ...

    @abstractmethod
    async def load(self, run_id: str) -> WorkflowRun | None: ...

    @abstractmethod
    async def save(self, run: WorkflowRun) -> None: ...

    @abstractmethod
    async def list_by_status(self, status: str) -> list[WorkflowRun]: ...


class InMemoryRunStore(WorkflowRunStore):
    """Non-durable store for dev/tests. Deep-copies on the boundary to avoid aliasing."""

    def __init__(self):
        self._runs: dict[str, WorkflowRun] = {}

    async def create(self, run: WorkflowRun) -> None:
        self._runs[run.run_id] = copy.deepcopy(run)

    async def load(self, run_id: str) -> WorkflowRun | None:
        r = self._runs.get(run_id)
        return copy.deepcopy(r) if r is not None else None

    async def save(self, run: WorkflowRun) -> None:
        self._runs[run.run_id] = copy.deepcopy(run)

    async def list_by_status(self, status: str) -> list[WorkflowRun]:
        return [copy.deepcopy(r) for r in self._runs.values() if r.status == status]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_run_store.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix astromesh/workflow/store.py tests/test_workflow_run_store.py
git add astromesh/workflow/store.py tests/test_workflow_run_store.py
git commit -m "feat(workflow): WorkflowRunStore (ABC) + InMemoryRunStore"
```

---

### Task 4: `SqliteRunStore` (durable, offline-testable)

**Files:**
- Modify: `astromesh/workflow/store.py`
- Test: `tests/test_workflow_run_store.py` (agregar)

**Interfaces:**
- Consumes: `WorkflowRun`, `WorkflowRunStore` (Tasks 1, 3).
- Produces: `SqliteRunStore(db_path)` con `initialize()` + los 4 métodos; persiste `context` como JSON.

- [ ] **Step 1: Write the failing test** (agregar a `tests/test_workflow_run_store.py`)

```python
async def test_sqlite_store_roundtrip(tmp_path):
    from astromesh.workflow.store import SqliteRunStore

    store = SqliteRunStore(str(tmp_path / "runs.db"))
    await store.initialize()
    await store.create(WorkflowRun(run_id="r1", workflow_name="w", status="running",
                                   current_index=0, context={"steps": {"a": {"output": 1}}}))
    loaded = await store.load("r1")
    assert loaded.context["steps"]["a"]["output"] == 1
    loaded.status = "suspended"
    loaded.current_index = 2
    await store.save(loaded)
    assert (await store.load("r1")).current_index == 2
    await store.create(WorkflowRun(run_id="r2", workflow_name="w", status="suspended",
                                   current_index=0, context={}))
    assert {r.run_id for r in await store.list_by_status("suspended")} == {"r1", "r2"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_run_store.py::test_sqlite_store_roundtrip -v`
Expected: FAIL — `ImportError: SqliteRunStore`.

- [ ] **Step 3: Write minimal implementation** (agregar a `astromesh/workflow/store.py`)

```python
import json

import aiosqlite


class SqliteRunStore(WorkflowRunStore):
    _COLS = ("run_id", "workflow_name", "status", "current_index", "context",
             "resume_key", "created_at", "updated_at", "expires_at", "error")

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS workflow_runs ("
            "run_id TEXT PRIMARY KEY, workflow_name TEXT, status TEXT, current_index INTEGER, "
            "context TEXT, resume_key TEXT, created_at TEXT, updated_at TEXT, "
            "expires_at TEXT, error TEXT)"
        )
        await self._db.commit()

    def _row(self, run: WorkflowRun) -> tuple:
        return (run.run_id, run.workflow_name, run.status, run.current_index,
                json.dumps(run.context), run.resume_key, run.created_at,
                run.updated_at, run.expires_at, run.error)

    def _from_row(self, row) -> WorkflowRun:
        return WorkflowRun(
            run_id=row[0], workflow_name=row[1], status=row[2], current_index=row[3],
            context=json.loads(row[4]) if row[4] else {}, resume_key=row[5],
            created_at=row[6], updated_at=row[7], expires_at=row[8], error=row[9])

    async def create(self, run: WorkflowRun) -> None:
        await self.save(run)

    async def save(self, run: WorkflowRun) -> None:
        placeholders = ", ".join("?" for _ in self._COLS)
        await self._db.execute(
            f"INSERT OR REPLACE INTO workflow_runs ({', '.join(self._COLS)}) "
            f"VALUES ({placeholders})",
            self._row(run),
        )
        await self._db.commit()

    async def load(self, run_id: str) -> WorkflowRun | None:
        cur = await self._db.execute(
            f"SELECT {', '.join(self._COLS)} FROM workflow_runs WHERE run_id = ?", (run_id,))
        row = await cur.fetchone()
        return self._from_row(row) if row else None

    async def list_by_status(self, status: str) -> list[WorkflowRun]:
        cur = await self._db.execute(
            f"SELECT {', '.join(self._COLS)} FROM workflow_runs WHERE status = ?", (status,))
        return [self._from_row(r) for r in await cur.fetchall()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_run_store.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix astromesh/workflow/store.py tests/test_workflow_run_store.py
git add astromesh/workflow/store.py tests/test_workflow_run_store.py
git commit -m "feat(workflow): SqliteRunStore (persistencia durable de corridas)"
```

---

### Task 5: Engine durable — `run` con checkpoint + suspend

**Files:**
- Modify: `astromesh/workflow/__init__.py`
- Test: `tests/test_workflow_durable_engine.py`

**Interfaces:**
- Consumes: `WorkflowRunStore`/`InMemoryRunStore` (Tasks 3), `StepStatus.SUSPENDED`, `WorkflowRun`, `WorkflowRunResult.run_id` (Task 1).
- Produces: `WorkflowEngine.__init__(..., store: WorkflowRunStore | None = None)`; `run(name, trigger)` durable con fachada síncrona (devuelve `WorkflowRunResult` con `run_id`; `status="suspended"` si golpea un wait).

**Contexto:** `WorkflowEngine.run` hoy es un loop `while i < len(wf.steps)` que ejecuta cada step, guarda outputs en `context["steps"][name]`, maneja `on_error` (goto), `switch goto`, y devuelve `WorkflowRunResult`. Hay que **preservar toda esa lógica** y agregar: crear un `WorkflowRun` en el store, `store.save` tras cada step, y cortar+persistir en `SUSPENDED`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_durable_engine.py
from astromesh.workflow.models import StepSpec, StepStatus, WorkflowSpec
from astromesh.workflow.store import InMemoryRunStore


class _StubExecutor:
    """Resuelve agent/tool a un output fijo; delega wait a un StepResult SUSPENDED."""
    def __init__(self):
        from astromesh.workflow.executor import StepExecutor
        self._real = StepExecutor(runtime=None, tool_registry=None)

    async def execute_step(self, step, context):
        from astromesh.workflow.models import StepResult
        if step.step_type.value == "wait":
            return await self._real.execute_step(step, context)
        return StepResult(name=step.name, status=StepStatus.SUCCESS, output={"ok": step.name})


def _engine(steps, store):
    from astromesh.workflow import WorkflowEngine
    eng = WorkflowEngine(workflows_dir="", runtime=None, tool_registry=None, store=store)
    eng._workflows = {"wf": WorkflowSpec(name="wf", steps=steps)}
    eng._executor = _StubExecutor()
    return eng


async def test_run_without_wait_returns_full_result():
    store = InMemoryRunStore()
    eng = _engine([StepSpec(name="a", tool="t"), StepSpec(name="b", tool="t")], store)
    result = await eng.run("wf", trigger={"x": 1})
    assert result.status == "completed"
    assert result.run_id is not None
    assert result.steps["a"].output == {"ok": "a"}
    assert (await store.load(result.run_id)).status == "completed"


async def test_run_with_wait_suspends_and_persists():
    store = InMemoryRunStore()
    eng = _engine(
        [StepSpec(name="a", tool="t"),
         StepSpec(name="w", wait={"resume_key": "k"}),
         StepSpec(name="b", tool="t")],
        store)
    result = await eng.run("wf", trigger={})
    assert result.status == "suspended"
    saved = await store.load(result.run_id)
    assert saved.status == "suspended"
    assert saved.current_index == 2          # posterior al wait (índice de "b")
    assert saved.context["steps"]["a"]["output"] == {"ok": "a"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_durable_engine.py -v`
Expected: FAIL — `WorkflowEngine.__init__` no acepta `store` / no persiste / no suspende.

- [ ] **Step 3: Write minimal implementation**

En `astromesh/workflow/__init__.py`:

(a) `__init__`: agregar `store: "WorkflowRunStore | None" = None` y `self._store = store`. Import arriba: `from astromesh.workflow.store import InMemoryRunStore, WorkflowRunStore`. Si `store is None`, `self._store = InMemoryRunStore()`.

(b) Reescribir `run` para que sea durable. Estructura (preservando la lógica de steps/on_error/switch/tracing existente):
```python
    async def run(self, workflow_name, trigger):
        import uuid
        from datetime import UTC, datetime
        from astromesh.workflow.models import StepStatus, WorkflowRun, WorkflowRunResult

        wf = self._workflows.get(workflow_name)
        if not wf:
            raise ValueError(f"Workflow '{workflow_name}' not found")

        run = WorkflowRun(
            run_id=str(uuid.uuid4()), workflow_name=workflow_name, status="running",
            current_index=0, context={"trigger": trigger, "steps": {}},
            created_at=datetime.now(UTC).isoformat())
        await self._store.create(run)
        return await self._drive(wf, run)

    async def _drive(self, wf, run):
        """Ejecuta desde run.current_index; checkpoint por-step; corta en SUSPENDED."""
        from datetime import UTC, datetime, timedelta
        from astromesh.workflow.models import StepStatus, StepType, WorkflowRunResult

        step_index = {s.name: i for i, s in enumerate(wf.steps)}
        context = run.context
        step_results = {}
        status = "completed"
        i = run.current_index

        while i < len(wf.steps):
            step = wf.steps[i]
            result = await self._executor.execute_step(step, context)
            step_results[step.name] = result

            if result.status == StepStatus.SUSPENDED:
                run.status = "suspended"
                run.current_index = i + 1          # se retoma después del wait
                run.resume_key = (result.output or {}).get("resume_key")
                timeout = (result.output or {}).get("timeout_seconds")
                if timeout:
                    run.expires_at = (datetime.now(UTC) + timedelta(seconds=timeout)).isoformat()
                run.updated_at = datetime.now(UTC).isoformat()
                await self._store.save(run)
                return WorkflowRunResult(workflow_name=wf.name, status="suspended",
                                         steps=step_results, run_id=run.run_id)

            if result.status == StepStatus.ERROR:
                context["steps"][step.name] = {"output": result.output, "error": result.error}
                run.current_index = i
                run.updated_at = datetime.now(UTC).isoformat()
                await self._store.save(run)
                if step.on_error and step.on_error != "fail" and step.on_error in step_index:
                    i = step_index[step.on_error]
                    continue
                status = "failed"
                run.error = result.error
                break

            context["steps"][step.name] = {"output": result.output}

            if step.step_type == StepType.SWITCH and result.output:
                goto = result.output.get("goto")
                if goto and goto in step_index:
                    goto_step = wf.steps[step_index[goto]]
                    goto_result = await self._executor.execute_step(goto_step, context)
                    step_results[goto_step.name] = goto_result
                    if goto_result.status == StepStatus.ERROR:
                        status = "failed"
                    else:
                        context["steps"][goto_step.name] = {"output": goto_result.output}
                    break

            run.current_index = i + 1
            run.updated_at = datetime.now(UTC).isoformat()
            await self._store.save(run)
            i += 1

        run.status = status
        run.updated_at = datetime.now(UTC).isoformat()
        await self._store.save(run)
        return WorkflowRunResult(workflow_name=wf.name, status=status,
                                 steps=step_results, run_id=run.run_id)
```

Nota: esta reescritura **preserva** on_error/switch/goto. Si el `run` original tenía tracing (spans), reincorporá las mismas llamadas de tracing dentro del loop (no es el foco del test, pero no lo quites). Mantené la firma pública `run(workflow_name, trigger)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_durable_engine.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Regresión + lint + commit**

```bash
uv run pytest tests/ -k workflow -q
uv run ruff check --fix astromesh/workflow/__init__.py tests/test_workflow_durable_engine.py
git add astromesh/workflow/__init__.py tests/test_workflow_durable_engine.py
git commit -m "feat(workflow): engine durable (checkpoint por-step + suspend, fachada síncrona)"
```

---

### Task 6: Engine — `resume(run_id, payload)`

**Files:**
- Modify: `astromesh/workflow/__init__.py`
- Test: `tests/test_workflow_resume.py`

**Interfaces:**
- Consumes: `WorkflowEngine._drive` + `self._store` (Task 5).
- Produces: `WorkflowEngine.resume(run_id, payload) -> WorkflowRunResult` (409-equivalente: lanza `ValueError` si la corrida no está `suspended`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_resume.py
import pytest

from astromesh.workflow.models import StepSpec, StepStatus, WorkflowSpec
from astromesh.workflow.store import InMemoryRunStore


class _StubExecutor:
    def __init__(self):
        from astromesh.workflow.executor import StepExecutor
        self._real = StepExecutor(runtime=None, tool_registry=None)

    async def execute_step(self, step, context):
        from astromesh.workflow.models import StepResult
        if step.step_type.value == "wait":
            return await self._real.execute_step(step, context)
        # 'b' expone el payload del resume para poder asertarlo
        return StepResult(name=step.name, status=StepStatus.SUCCESS,
                          output={"seen_resume": context.get("resume")})


def _engine(store):
    from astromesh.workflow import WorkflowEngine
    eng = WorkflowEngine(workflows_dir="", runtime=None, tool_registry=None, store=store)
    eng._workflows = {"wf": WorkflowSpec(name="wf", steps=[
        StepSpec(name="a", tool="t"),
        StepSpec(name="w", wait={"resume_key": "k"}),
        StepSpec(name="b", tool="t")])}
    eng._executor = _StubExecutor()
    return eng


async def test_resume_continues_to_completion():
    store = InMemoryRunStore()
    eng = _engine(store)
    r1 = await eng.run("wf", trigger={})
    assert r1.status == "suspended"
    r2 = await eng.resume(r1.run_id, payload={"amount": 100})
    assert r2.status == "completed"
    assert r2.steps["b"].output == {"seen_resume": {"amount": 100}}
    assert (await store.load(r1.run_id)).status == "completed"


async def test_resume_from_fresh_store_instance_is_durable():
    store = InMemoryRunStore()
    r1 = await _engine(store).run("wf", trigger={})
    # nuevo engine, MISMO store (simula otro proceso)
    eng2 = _engine(store)
    r2 = await eng2.resume(r1.run_id, payload={"amount": 5})
    assert r2.status == "completed"


async def test_resume_non_suspended_raises():
    store = InMemoryRunStore()
    eng = _engine(store)
    r1 = await eng.run("wf", trigger={})
    await eng.resume(r1.run_id, payload={})           # completa
    with pytest.raises(ValueError):
        await eng.resume(r1.run_id, payload={})       # ya no está suspended
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_resume.py -v`
Expected: FAIL — `WorkflowEngine` no tiene `resume`.

- [ ] **Step 3: Write minimal implementation** (agregar a `WorkflowEngine`)

```python
    async def resume(self, run_id, payload):
        from astromesh.workflow.models import WorkflowRunResult
        run = await self._store.load(run_id)
        if run is None:
            raise ValueError(f"Run '{run_id}' not found")
        if run.status != "suspended":
            raise ValueError(f"Run '{run_id}' is not suspended (status={run.status})")

        wf = self._workflows.get(run.workflow_name)
        if not wf:
            raise ValueError(f"Workflow '{run.workflow_name}' not found")

        # el step wait está en current_index-1; inyectar el payload como su output
        wait_idx = run.current_index - 1
        if 0 <= wait_idx < len(wf.steps):
            run.context["steps"][wf.steps[wait_idx].name] = {"output": payload}
        run.context["resume"] = payload
        run.status = "running"
        await self._store.save(run)
        return await self._drive(wf, run)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_resume.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix astromesh/workflow/__init__.py tests/test_workflow_resume.py
git add astromesh/workflow/__init__.py tests/test_workflow_resume.py
git commit -m "feat(workflow): resume(run_id, payload) — retoma corrida suspendida"
```

---

### Task 7: Sweeps — `sweep_expired` + `mark_orphaned_failed`

**Files:**
- Modify: `astromesh/workflow/__init__.py`
- Test: `tests/test_workflow_sweeps.py`

**Interfaces:**
- Consumes: `self._store.list_by_status` + `save` (Task 3).
- Produces: `WorkflowEngine.sweep_expired(now: str) -> int`; `WorkflowEngine.mark_orphaned_failed() -> int`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_sweeps.py
from astromesh.workflow.models import WorkflowRun
from astromesh.workflow.store import InMemoryRunStore


def _engine(store):
    from astromesh.workflow import WorkflowEngine
    return WorkflowEngine(workflows_dir="", runtime=None, tool_registry=None, store=store)


async def test_sweep_expired_marks_expired():
    store = InMemoryRunStore()
    await store.create(WorkflowRun(run_id="r1", workflow_name="w", status="suspended",
                                   current_index=1, context={}, expires_at="2026-01-01T00:00:00+00:00"))
    await store.create(WorkflowRun(run_id="r2", workflow_name="w", status="suspended",
                                   current_index=1, context={}, expires_at="2999-01-01T00:00:00+00:00"))
    n = await _engine(store).sweep_expired(now="2026-06-01T00:00:00+00:00")
    assert n == 1
    assert (await store.load("r1")).status == "expired"
    assert (await store.load("r2")).status == "suspended"


async def test_mark_orphaned_failed():
    store = InMemoryRunStore()
    await store.create(WorkflowRun(run_id="a", workflow_name="w", status="running",
                                   current_index=0, context={}))
    await store.create(WorkflowRun(run_id="b", workflow_name="w", status="suspended",
                                   current_index=1, context={}))
    n = await _engine(store).mark_orphaned_failed()
    assert n == 1
    assert (await store.load("a")).status == "failed"
    assert (await store.load("b")).status == "suspended"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_sweeps.py -v`
Expected: FAIL — métodos inexistentes.

- [ ] **Step 3: Write minimal implementation** (agregar a `WorkflowEngine`)

```python
    async def sweep_expired(self, now: str) -> int:
        n = 0
        for run in await self._store.list_by_status("suspended"):
            if run.expires_at and run.expires_at < now:
                run.status = "expired"
                run.error = "wait timed out"
                await self._store.save(run)
                n += 1
        return n

    async def mark_orphaned_failed(self) -> int:
        n = 0
        for run in await self._store.list_by_status("running"):
            run.status = "failed"
            run.error = "orphaned: process died mid-run"
            await self._store.save(run)
            n += 1
        return n
```

(Comparar `expires_at < now` como strings ISO-8601 UTC es correcto por orden lexicográfico cuando el formato es homogéneo — ambos se generan con `datetime.now(UTC).isoformat()`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_sweeps.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix astromesh/workflow/__init__.py tests/test_workflow_sweeps.py
git add astromesh/workflow/__init__.py tests/test_workflow_sweeps.py
git commit -m "feat(workflow): sweeps de expiración y de corridas huérfanas (failed)"
```

---

### Task 8: API — run (fachada) + get + resume

**Files:**
- Modify: `astromesh/api/routes/workflows.py`
- Test: `tests/test_workflow_durable_api.py`

**Interfaces:**
- Consumes: `engine.run`/`resume`/`_store` (Tasks 5, 6).
- Produces: `POST /workflows/{name}/run` (fachada: full result o `{run_id, status}`); `GET /workflows/runs/{run_id}`; `POST /workflows/runs/{run_id}/resume`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_durable_api.py
import pytest

from astromesh.api.routes import workflows as wf_route
from astromesh.workflow.models import StepSpec, StepStatus, WorkflowSpec
from astromesh.workflow.store import InMemoryRunStore


class _StubExecutor:
    def __init__(self):
        from astromesh.workflow.executor import StepExecutor
        self._real = StepExecutor(runtime=None, tool_registry=None)

    async def execute_step(self, step, context):
        from astromesh.workflow.models import StepResult
        if step.step_type.value == "wait":
            return await self._real.execute_step(step, context)
        return StepResult(name=step.name, status=StepStatus.SUCCESS, output={"ok": step.name})


@pytest.fixture
def wired(monkeypatch):
    from astromesh.workflow import WorkflowEngine
    store = InMemoryRunStore()
    eng = WorkflowEngine(workflows_dir="", runtime=None, tool_registry=None, store=store)
    eng._workflows = {"wf": WorkflowSpec(name="wf", steps=[
        StepSpec(name="w", wait={"resume_key": "k"}), StepSpec(name="b", tool="t")])}
    eng._executor = _StubExecutor()
    wf_route.set_workflow_engine(eng)
    return eng


async def test_run_suspends_then_get_then_resume(client, wired):
    r = await client.post("/workflows/wf/run", json={"trigger": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "suspended" and body["run_id"]
    run_id = body["run_id"]

    g = await client.get(f"/workflows/runs/{run_id}")
    assert g.status_code == 200 and g.json()["status"] == "suspended"

    res = await client.post(f"/workflows/runs/{run_id}/resume", json={"payload": {"amount": 9}})
    assert res.status_code == 200 and res.json()["status"] == "completed"


async def test_resume_non_suspended_409(client, wired):
    r = await client.post("/workflows/wf/run", json={"trigger": {}})
    run_id = r.json()["run_id"]
    await client.post(f"/workflows/runs/{run_id}/resume", json={"payload": {}})  # completa
    again = await client.post(f"/workflows/runs/{run_id}/resume", json={"payload": {}})
    assert again.status_code == 409


async def test_get_unknown_run_404(client, wired):
    g = await client.get("/workflows/runs/nope")
    assert g.status_code == 404
```

(Usa el fixture `client` de `tests/conftest.py`, como los demás tests de API.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_durable_api.py -v`
Expected: FAIL — endpoints de runs inexistentes; `/run` no devuelve `run_id`.

- [ ] **Step 3: Write minimal implementation**

En `astromesh/api/routes/workflows.py`:

(a) `run_workflow`: tras `result = await _engine.run(...)`, si `result.status == "suspended"`:
```python
        return {"run_id": result.run_id, "status": result.status}
```
si no, agregar `"run_id": result.run_id` al dict de respuesta existente.

(b) Nuevos endpoints:
```python
class ResumeRequest(BaseModel):
    payload: dict[str, Any] = {}


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    if not _engine:
        raise HTTPException(status_code=503, detail="Workflow engine not initialized")
    run = await _engine._store.load(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return {"run_id": run.run_id, "workflow_name": run.workflow_name,
            "status": run.status, "current_index": run.current_index,
            "context": run.context, "error": run.error}


@router.post("/runs/{run_id}/resume")
async def resume_run(run_id: str, request: ResumeRequest):
    if not _engine:
        raise HTTPException(status_code=503, detail="Workflow engine not initialized")
    try:
        result = await _engine.resume(run_id, request.payload)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    if result.status == "suspended":
        return {"run_id": result.run_id, "status": result.status}
    return {"run_id": result.run_id, "status": result.status,
            "steps": {k: {"status": v.status.value, "output": v.output, "error": v.error}
                      for k, v in result.steps.items()}}
```

(Cuidado con el orden de rutas: `/runs/{run_id}` no debe colisionar con `/{name}`. Como `/runs/...` es literal, FastAPI lo matchea antes que `/{name}` si se declara; si hay ambigüedad, declarar los `runs` endpoints ANTES del `GET /{name}`. Verificar en el test que `GET /workflows/runs/...` no caiga en `get_workflow`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_durable_api.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix astromesh/api/routes/workflows.py tests/test_workflow_durable_api.py
git add astromesh/api/routes/workflows.py tests/test_workflow_durable_api.py
git commit -m "feat(workflow): API run (fachada) + GET /runs/{id} + POST /runs/{id}/resume"
```

---

### Task 9: Wiring — inyectar store al engine + sweeps al bootstrap

**Files:**
- Modify: `astromesh/workflow/__init__.py` (bootstrap corre los sweeps) y el sitio donde se construye el `WorkflowEngine`.
- Test: `tests/test_workflow_durable_engine.py` (agregar un test de bootstrap)

**Interfaces:**
- Consumes: `mark_orphaned_failed`/`sweep_expired` (Task 7), `store.initialize` (Task 4).
- Produces: `WorkflowEngine.bootstrap()` inicializa el store (si tiene `initialize`) y corre `mark_orphaned_failed()` + `sweep_expired(now)`.

- [ ] **Step 1: Write the failing test** (agregar a `tests/test_workflow_durable_engine.py`)

```python
async def test_bootstrap_runs_orphan_sweep(tmp_path, monkeypatch):
    from astromesh.workflow import WorkflowEngine
    from astromesh.workflow.models import WorkflowRun
    from astromesh.workflow.store import InMemoryRunStore

    store = InMemoryRunStore()
    await store.create(WorkflowRun(run_id="orphan", workflow_name="w", status="running",
                                   current_index=0, context={}))
    eng = WorkflowEngine(workflows_dir=str(tmp_path), runtime=None, tool_registry=None, store=store)
    await eng.bootstrap()
    assert (await store.load("orphan")).status == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_durable_engine.py::test_bootstrap_runs_orphan_sweep -v`
Expected: FAIL — `bootstrap` no corre el sweep (la corrida sigue en `running`).

- [ ] **Step 3: Write minimal implementation**

(a) En `WorkflowEngine.bootstrap`, después de cargar workflows y crear el executor, agregar:
```python
        from datetime import UTC, datetime
        if hasattr(self._store, "initialize"):
            await self._store.initialize()
        await self.mark_orphaned_failed()
        await self.sweep_expired(now=datetime.now(UTC).isoformat())
```

(b) Sitio de construcción del `WorkflowEngine`: buscarlo (`grep -rn "WorkflowEngine(" astromesh --include=*.py` — probablemente en un bootstrap de runtime/main). Pasar un `store` por defecto (`SqliteRunStore` con un path de config, o `InMemoryRunStore` si no hay config de DB). Si el constructor ya default-ea a `InMemoryRunStore` (Task 5), esto es opcional; documentá qué store queda por defecto en producción. Si no encontrás un sitio de construcción explícito (el engine se crea perezosamente), dejá el default del constructor y anotalo en el reporte.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_durable_engine.py -v`
Expected: PASS (incl. el nuevo test de bootstrap).

- [ ] **Step 5: Suite completa + lint + commit**

```bash
uv run pytest tests/ -k workflow -q
uv run ruff check .
git add astromesh/workflow/__init__.py tests/test_workflow_durable_engine.py
git commit -m "feat(workflow): bootstrap inicializa store + corre sweeps (huérfanas/expiradas)"
```

---

## Self-Review

**1. Spec coverage:**
- §1 primitiva `wait` (StepType.WAIT + SUSPENDED + StepSpec.wait + executor) → Tasks 1, 2. ✓
- §2 `WorkflowRunStore` + `WorkflowRun` + backends (InMemory + Sqlite; **Pg deferido**, documentado en Global Constraints) → Tasks 1, 3, 4. ✓ (divergencia Pg consciente)
- §3 engine durable + checkpoint + suspend + resume + fachada síncrona → Tasks 5, 6. ✓
- §4 API run/get/resume → Task 8. ✓
- §5 sweeps expiración + huérfanas→failed → Task 7; bootstrap → Task 9. ✓
- §Testing (InMemoryRunStore + stubs, determinista) → todos los tests de tarea. ✓
- §Criterios 1-7 → Task 5(1,3), 6(2,4), 7(5), 4(6), todas(7). ✓
- §Fuera de alcance (approval, crash-auto-resume, bus de eventos, exactly-once, follow-up Clarus) → sin tareas, correcto. ✓

**2. Placeholder scan:** cada step trae código o comando concreto. Las notas condicionales (marcador asyncio, sitio de construcción del engine, orden de rutas) son contingencias con acción exacta, no placeholders. La reescritura de `run` (Task 5) trae el método completo. ✓

**3. Type consistency:**
- `WorkflowRun(run_id, workflow_name, status, current_index, context, resume_key, created_at, updated_at, expires_at, error)` — Task 1, usado idéntico en Tasks 3/4/5/6/7. ✓
- `WorkflowRunStore.{create,load,save,list_by_status}` — Task 3, usado en 4/5/6/7/8/9. ✓
- `WorkflowEngine.__init__(workflows_dir, runtime, tool_registry, store=None)` — Task 5, usado en 6/7/8/9. ✓
- `run(name, trigger) -> WorkflowRunResult(.run_id,.status)` / `resume(run_id, payload)` / `_drive(wf, run)` / `sweep_expired(now)` / `mark_orphaned_failed()` — firmas consistentes entre definición (5/6/7) y llamadas (8/9). ✓
- `StepResult(name, status, output, error, duration_ms)` — existente, reusado en executor (Task 2) y stubs de test. ✓
