# Atlas Slice 2 (parte 3) — HITL Approval (aprobación humana durable)

**Fecha:** 2026-07-11
**Estado:** aprobado (brainstorming) → listo para plan
**Depende de:** async durable (`2026-07-10-atlas-slice2-async-durable-design.md`) — reusa suspend/resume/store/sweeps.

## Objetivo

Agregar un tipo de step de **aprobación humana** a los workflows de astromesh: el workflow
se suspende de forma durable en un punto de decisión, expone una **cola de aprobaciones
pendientes**, y continúa (o se desvía) cuando un humano aprueba/rechaza — reutilizando por
completo la maquinaria durable ya construida (WAIT/SUSPENDED, `WorkflowRun`, `WorkflowRunStore`,
resume, sweeps).

## Alcance y no-alcance (decisión de arquitectura)

astromesh **no tiene sistema de identidad ni de authz** (la API solo tiene CORS; las rutas de
workflow no tienen `Depends`/auth/principal). Por lo tanto el HITL es **record-only**:

- astromesh **registra** el aprobador requerido (declarativo en el YAML) y **registra** la
  decisión (quién/cuándo/comentario, provistos por el caller).
- astromesh **no autentica ni autoriza** al aprobador. Enforcing "quién puede aprobar" es
  responsabilidad de la aplicación que consume la API (p. ej. el futuro cockpit de Clarus).

Esto mantiene el alcance coherente con la arquitectura actual y evita construir un sistema de
identidad fuera de este slice.

## Diseño

### 1. Modelo del step: `StepType.APPROVAL`

Un WAIT especializado. Forma en YAML:

```yaml
- name: aprobar-orden
  approval:
    approver: "role:finance_manager"   # requisito declarativo (string libre); NO enforced por astromesh
    prompt: "Aprobar la orden de compra de $12.500"
    on_reject: notificar-rechazo       # opcional: step al que saltar si se rechaza
    timeout_seconds: 86400             # opcional: si vence → rechazo automático
```

Cambios en `astromesh/workflow/models.py`:

- `StepType.APPROVAL = "approval"`.
- `StepSpec.approval: dict | None = None`, sumado a la **exclusión mutua** de step-types en
  `__post_init__` (hoy cuenta `agent, tool, switch, wait`; pasa a incluir `approval` → exactamente uno).
- `step_type` devuelve `StepType.APPROVAL` cuando `approval is not None`.
- Nuevo estado terminal `WorkflowRunStatus.REJECTED` (`"rejected"`), distinto de `failed`/`expired`.
  (Hoy `WorkflowRun.status` es un `str`; se agrega `"rejected"` a los valores válidos documentados en el comentario.)
- `WorkflowRun` gana `pending_approval: dict | None = None` — metadatos del approval activo que
  alimentan la cola: `{"step_name", "approver", "prompt"}`. Persiste y sobrevive load/save en el store.

### 2. Executor: `_run_approval`

En `astromesh/workflow/executor.py`, análogo a `_run_wait`:

```python
elif step.step_type == StepType.APPROVAL:
    return self._run_approval(step)
```

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

Suspende igual que un WAIT, pero el `output` lleva los metadatos de aprobación.

### 3. Engine: suspensión, decisión y ruteo

En `astromesh/workflow/__init__.py`, `_drive` ya trata `SUSPENDED` (checkpoint + `current_index =
i + 1` + `resume_key` + `expires_at` desde `timeout_seconds`). Se extiende para que, cuando el
`output` traiga `pending_approval`, lo guarde en `run.pending_approval` antes de persistir. Esto
aplica tanto en el bloque principal de SUSPENDED como en el sub-bloque de switch-goto (el mismo
lugar donde el fix `8104220` agregó el manejo de SUSPENDED).

**Resolución** — se realiza inyectando un **registro de decisión** en el `context` bajo el nombre
del step, y luego continuando o desviando:

```python
context[step_name] = {
    "approved": bool,
    "approver": str,
    "comment": str | None,
    "decided_at": <ISO ts provisto por el caller o el sweep>,
}
```

- **Aprobación:** limpia `run.pending_approval`, continúa desde `current_index` (que ya apunta al
  step siguiente al approval), reusa el camino de resume normal.
- **Rechazo:** limpia `run.pending_approval` e inyecta la decisión con `approved: false`. Luego:
  - si el step declara `on_reject` → `run.current_index = step_index[on_reject]` (reusa el goto del
    switch), y sigue driveando desde ahí;
  - si **no** declara `on_reject` → `run.status = "rejected"` (terminal), persiste y termina.
- En ambos casos, como la decisión queda en `context[step_name]`, cualquier `switch` posterior
  puede rutear leyendo `context[step_name].approved` — sin maquinaria nueva.

Nota: `decided_at` lo provee el caller (o el sweep con la marca de tiempo del barrido). El engine no
llama `datetime.now()` en el camino de decisión que dependa de reproducibilidad; recibe el ts.

### 4. Timeout (sweep)

Hoy `sweep_expired(now)` marca todo run suspendido con `expires_at < now` como `status="expired"`,
`error="wait timed out"`. Se **extiende** para distinguir approvals:

- Si el run vencido tiene `pending_approval` (es un APPROVAL) → en vez de `expired`, inyecta la
  decisión `{approved: false, approver: "system:timeout", comment: null, decided_at: now}` y **reusa
  el camino de rechazo** (salta a `on_reject` si el step lo declara, o marca `rejected`).
- Si el run vencido es un WAIT no-approval → sigue yendo a `expired` como hoy (sin cambios).
- Si el APPROVAL **no** declaró `timeout_seconds` → `expires_at is None` → el sweep no lo toca:
  queda pendiente hasta acción humana (default sin auto-resolución).

Para saltar a `on_reject` desde el sweep, el sweep necesita el `WorkflowSpec` del run (para resolver
`on_reject` y seguir driveando). Reusa `get_workflow(run.workflow_name)` + `_drive`/el mismo helper
de rechazo que usan los endpoints, de modo que timeout y reject manual compartan exactamente el
mismo código de resolución.

### 5. API (record-only)

Rutas nuevas en `astromesh/api/routes/workflows.py` (router con `prefix="/workflows"`, montado bajo
`/v1`). **Declaradas antes de `/{name}`** (junto a `/runs`, para no colisionar con el catch-all):

```
GET  /v1/workflows/approvals[?approver=role:finance_manager]
        → [{run_id, workflow_name, step_name, approver, prompt, created_at, expires_at}, ...]
          runs en estado "suspended" con pending_approval != null; filtro opcional por approver exacto.

POST /v1/workflows/runs/{run_id}/approve   body: {approver: str, comment?: str}
        → {run_id, status}   (status = "completed" | "suspended" si hay otro wait/approval después)

POST /v1/workflows/runs/{run_id}/reject    body: {approver: str, comment?: str}
        → {run_id, status}   (status = "rejected" | "running"/"suspended"/"completed" si hay on_reject)
```

- `approve`/`reject` son **fachada sobre el resume durable**: arman el registro de decisión
  (`decided_at` sellado por el endpoint) y llaman a la maquinaria de resolución del engine.
- **Mapeo de errores** (reusa el patrón del `resume` existente):
  - `404` si el run no existe.
  - `409` si el run **no** está suspendido en un APPROVAL (ya decidido, terminal, o el step actual no
    es un approval) → idempotencia natural contra doble-aprobación / carreras.
  - `503` si el engine no está inicializado (igual que las demás rutas).
- `approver` en el body es **registro, no verificación**: astromesh no valida identidad.

Se agregan métodos en el engine para dar soporte limpio a los endpoints:
`list_pending_approvals(approver: str | None) -> list[WorkflowRun]`,
`approve(run_id, approver, comment, decided_at) -> WorkflowRunResult`,
`reject(run_id, approver, comment, decided_at) -> WorkflowRunResult`.
`approve`/`reject` validan que el run esté `suspended` con `pending_approval` (si no → error que el
endpoint mapea a 404/409, mismo patrón que `resume`).

## Testing

Correr los **tres** antes de declarar verde (la CI de astromesh incluye mypy):
`uv run pytest` + `uv run ruff check` + `uv run mypy src/`.

- **models/store**: APPROVAL entra en la exclusión mutua de step-types (0 o 2 tipos → ValueError que
  menciona `approval`); `step_type` == APPROVAL; `pending_approval` persiste y sobrevive load/save;
  `REJECTED` reconocido como estado terminal.
- **executor**: `_run_approval` → SUSPENDED con `output` que incluye `pending_approval`, `approver`,
  `prompt`, `on_reject`, `resume_key`, `timeout_seconds`.
- **engine**:
  - approve → continúa; `context[step].approved == true`; `pending_approval` limpiado.
  - reject con `on_reject` → salta al step declarado; `context[step].approved == false`.
  - reject sin `on_reject` → run `rejected`.
  - un `switch` posterior rutea por `context[step].approved` (prueba de integración del ruteo).
  - approve/reject sobre run inexistente o no-suspendido-en-approval → error (404/409).
- **sweep**: APPROVAL vencido con `on_reject` → salta; APPROVAL vencido sin `on_reject` → `rejected`;
  decisión con `approver == "system:timeout"`; APPROVAL sin `timeout_seconds` → intacto; WAIT
  no-approval vencido → sigue `expired`.
- **API**: `GET /approvals` (con y sin filtro `approver`) devuelve la cola con prompt/approver;
  `approve`/`reject` 200 con `{run_id, status}`; 404 run inexistente; 409 doble-approve / run no
  suspendido en approval.

## Fuera de alcance

- Identidad/authz del aprobador (delegado a la app llamante).
- UI/cockpit de aprobaciones (Slice 3).
- Notificaciones/push al aprobador (el caller consume `GET /approvals`).
- Persistencia Postgres del run store (`PgRunStore`) — sigue diferida como en async durable.
- Delegación/escalado de aprobaciones y aprobación multi-firma (N-de-M).
