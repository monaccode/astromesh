# CLARUS Atlas — Slice 2 (parte 2): Ejecución durable de workflows (async wait/resume)

> **Contexto de roadmap.** Segunda pieza del **Slice 2** de CLARUS Atlas. El reporte
> de capability-gaps del Slice 1 identificó tres cosas que el runtime de astromesh no
> ejecuta: `kb_wiring` (RAG — cerrado en la parte 1), **`async`** (esperas durables) y
> `approval` (HITL). Este spec cierra **`async`**: la **fundación de ejecución durable**
> sobre la que después se construye el **approval** (un `WAIT` especializado).
>
> **Repo de trabajo:** `astromesh`. No toca `clarus-platform` (el follow-up de que Atlas
> emita workflows con steps `wait` es una tarea posterior, ver §Fuera de alcance).

## Objetivo

Que un `Workflow` de astromesh pueda **suspenderse en un punto de espera** (aguardando
un evento externo que puede tardar minutos o días) y **resumir después** desde donde
quedó, sin mantener un proceso vivo y **sobreviviendo a reinicios**. Concretamente:

1. Un step nuevo `wait` pausa la corrida hasta que la resuman por API.
2. El estado de cada corrida se **persiste paso a paso** en un store durable.
3. `POST /workflows/{name}/run` mantiene su **fachada síncrona**: si la corrida termina
   sin suspender, devuelve el resultado completo como hoy; si golpea un `wait`, devuelve
   `{run_id, status: "suspended"}`.
4. `POST /workflows/runs/{run_id}/resume` continúa una corrida suspendida.
5. Las esperas vencidas y las corridas huérfanas (proceso muerto) se resuelven de forma
   segura.

## Enfoque elegido: (C) engine durable con fachada síncrona

De tres enfoques evaluados —(A) durable-by-default con API 100% async, (B) durabilidad
solo al suspender (híbrido), (C) engine durable con fachada síncrona— se eligió **(C)**:
el engine **siempre persiste paso a paso** (habilita crash-recovery real), pero la API
sigue pudiendo bloquear: corrida simple → resultado completo (contrato actual intacto);
corrida que suspende → `run_id` + `suspended`. Es incremental sin romper lo existente.

## Estado actual (con evidencia)

- `WorkflowEngine.run(name, trigger)` (`astromesh/workflow/__init__.py:39`) es **una
  corutina en memoria**: itera `wf.steps` por índice `i`, mantiene
  `context = {"trigger": ..., "steps": {name: {"output": ...}}}`, resuelve `on_error`
  (goto a un step) y `switch goto`, y devuelve un `WorkflowRunResult` **bloqueando**.
  **No hay run-id ni persistencia** — si el proceso muere, la corrida se pierde.
- `StepType` (`astromesh/workflow/models.py:9`) = `AGENT | TOOL | SWITCH`. **No existe
  ninguna noción de espera/suspensión.**
- `StepExecutor.execute_step` (`astromesh/workflow/executor.py:33`) despacha por tipo con
  retry/timeout `asyncio` (en memoria, no durable).
- `POST /workflows/{name}/run` (`astromesh/api/routes/workflows.py`) hace
  `await _engine.run(...)` y devuelve el resultado completo.
- **Infra de persistencia reusable:** backends pg/sqlite ya implementados para memoria
  (`astromesh/memory/backends/{pg,sqlite}_conv.py`) — patrón de acceso a DB a espejar.

## Arquitectura y componentes

### 1. La primitiva `wait` (nuevo step type)
`astromesh/workflow/models.py`:
- `StepType.WAIT = "wait"`.
- `StepStatus.SUSPENDED = "suspended"`.
- `StepSpec` gana un campo opcional `wait: dict | None` (paralelo a `agent`/`tool`/`switch`);
  `__post_init__` cuenta `wait` como el cuarto tipo mutuamente exclusivo. Forma del bloque:
  ```yaml
  - name: esperar-pago
    wait:
      resume_key: payment.confirmed      # etiqueta lógica del evento (correlación/docs)
      timeout_seconds: 604800            # opcional: 7 días → expira
  ```
- `StepExecutor._dispatch`: rama nueva para `WAIT` → devuelve
  `StepResult(name, status=SUSPENDED, output={"resume_key": ..., "timeout_seconds": ...})`.
  El `WAIT` es un **primitivo puro de pausa**: no hace trabajo, solo señala suspensión.
  (El patrón típico: un `tool` dispara la acción externa y el `wait` siguiente pausa hasta
  el callback.)

### 2. `WorkflowRunStore` (persistencia durable)
`astromesh/workflow/store.py` (nuevo), pluggable espejando `memory/backends`:
- Registro `WorkflowRun`: `run_id` (uuid str), `workflow_name`, `status`
  (`running|suspended|completed|failed|timed_out|expired`), `current_index` (int, próximo
  step a ejecutar al resumir), `context` (json), `resume_key` (str|None), `created_at`,
  `updated_at`, `expires_at` (str|None), `error` (str|None).
- Interfaz abstracta `WorkflowRunStore`:
  - `async create(run: WorkflowRun) -> None`
  - `async load(run_id: str) -> WorkflowRun | None`
  - `async save(run: WorkflowRun) -> None`  (upsert por run_id)
  - `async list_by_status(status: str) -> list[WorkflowRun]`  (para los sweeps)
- Backends: `InMemoryRunStore` (default dev + tests), `SqliteRunStore`, `PgRunStore`
  (mismo patrón lazy-pool que `pg_conv.py`). Selección por config del engine.

### 3. Engine durable + checkpointing
`astromesh/workflow/__init__.py` (`WorkflowEngine.run` reescrito para durabilidad):
- `run(name, trigger)` crea un `WorkflowRun(run_id, status="running", current_index=0,
  context={trigger, steps:{}})`, `store.create(...)`, y entra al loop desde `current_index`.
- Tras **cada step completado**: actualiza `context` + `current_index` y hace `store.save`
  (**checkpoint por-step** → crash-recovery). Semántica **at-least-once**: si el proceso
  muere durante un step, al recuperar ese step se re-ejecuta (los steps deberían ser
  idempotentes — se documenta; exactly-once queda fuera).
- Si un step devuelve `SUSPENDED`: setea `status="suspended"`, deja `current_index`
  apuntando al **step posterior al `wait`** (donde se retoma), calcula `expires_at` desde
  `timeout_seconds` (si hay), persiste, y **retorna** un `WorkflowRunResult` con
  `status="suspended"` + `run_id` (no sigue).
- Si el loop llega al final: `status="completed"`, persiste, retorna el resultado completo.
- Errores/`on_error`/`switch goto` mantienen la lógica actual, con checkpoint en cada
  transición.
- Se conserva el `WorkflowRunResult` actual, extendido con `run_id: str` y el status
  `"suspended"`.
- `resume(run_id, payload)`: `store.load`, valida `status=="suspended"`, inyecta el payload
  como output del step `WAIT` en `context["steps"][<wait_step>]` (y `context["resume"]=payload`),
  setea `status="running"`, y re-entra al mismo loop desde el `current_index` persistido (que
  ya quedó posterior al `wait`) hasta el próximo suspend/fin. Devuelve resultado o
  `run_id`+suspended (misma fachada).

### 4. API
`astromesh/api/routes/workflows.py`:
- `POST /workflows/{name}/run` → `await engine.run(...)`. Respuesta: si `status=="suspended"`
  → `{run_id, status}`; si no → el payload actual completo (retrocompatible) **+** `run_id`.
- `GET /workflows/runs/{run_id}` → estado + `context`/resultado parcial (404 si no existe).
- `POST /workflows/runs/{run_id}/resume` con body `{payload: {...}}` → `await engine.resume(...)`.
  409 si la corrida no está `suspended`; 404 si no existe.

### 5. Timeouts / expiración + huérfanas (sweeps)
- **Expiración:** el `timeout_seconds` del `WAIT` fija `expires_at`. Un sweep
  (`engine.sweep_expired()`, corrido al bootstrap) marca las `suspended` con
  `expires_at < now` como `expired` (ruteo a `on_error` si el wait lo define; si no,
  termina como `expired`).
- **Huérfanas (crash):** al bootstrap, `engine.mark_orphaned_failed()` marca toda corrida
  en `running` como `failed` (el proceso que la ejecutaba murió). *Decisión de este slice:*
  **se marcan `failed`**, no se auto-resumen — el auto-re-drive desde checkpoint queda como
  follow-up (evita abrir idempotencia de re-ejecución en esta fundación). Espejo del patrón
  `markOrphanedRunsFailed` de los orchestrators de Optimus/Atlas.
- *Nota:* `now`/timestamps se inyectan (no se llama a `datetime.now()` en el código puro que
  testeamos) para mantener los sweeps deterministas en test.

## Manejo de errores

- Un step que falla mantiene el `on_error` actual (goto o `fail`); el checkpoint se persiste
  igual, así una corrida fallida queda con su estado y `error`.
- `resume` sobre una corrida no-suspendida → 409 (no revive completadas/fallidas).
- Fallo del store al persistir → se propaga (una corrida durable que no puede persistir su
  checkpoint no debe seguir en silencio); se loguea. (A diferencia del RAG, acá la
  persistencia **es** el objetivo, no es aditiva.)

## Testing

Fakes deterministas: `InMemoryRunStore` + `runtime`/`tool_registry` stub + un
`StepExecutor` stub que resuelve steps `agent`/`tool` a outputs fijos. Casos:
- **Suspend:** un workflow con un step `wait` corre, suspende, devuelve `run_id`+`suspended`,
  y el store tiene la corrida en `suspended` con el `current_index` correcto.
- **Resume:** `resume(run_id, payload)` continúa hasta completar; el payload aparece en el
  `context` de los steps siguientes.
- **Fachada síncrona:** un workflow sin `wait` devuelve el `WorkflowRunResult` completo
  (contrato actual intacto) + `run_id`.
- **Durabilidad:** se carga la corrida desde el store (simulando otro proceso) y `resume`
  continúa correctamente.
- **Expiración:** `sweep_expired` con un `now` inyectado marca `expired` una `suspended`
  vencida.
- **Huérfanas:** `mark_orphaned_failed` marca `failed` las `running`.
- **Backends:** `SqliteRunStore` create/load/save/list_by_status round-trip.

`pytest` + `pytest-asyncio` + `ruff`, como el resto de astromesh.

## Fuera de alcance (YAGNI — slices/piezas posteriores)

- **HITL approval** (la tercera pieza del Slice 2): un `WAIT` especializado con identidad
  del aprobador + endpoints approve/reject + registro de decisión. Este spec deja el `WAIT`
  genérico justamente para que approval lo especialice.
- **Crash-auto-resume**: re-drive automático de corridas `running` huérfanas desde el último
  checkpoint (acá se marcan `failed`).
- **Bus de eventos / correlación por clave de negocio**: el resume es por `run_id` (el
  `resume_key` se persiste para un lookup futuro, pero no hay endpoint de resume-por-evento).
- **Timers/schedules durables** (cron-like dentro del workflow), **exactly-once** (acá
  at-least-once), y **reintento durable** con backoff persistido.
- **Clarus / Atlas**: que el generador de blueprints emita workflows con steps `wait` en los
  pasos async que ya detecta — follow-up en `clarus-platform` una vez que el runtime lo
  soporte (análogo al puente `spec.knowledge` del RAG).

## Criterios de aceptación

1. Un workflow con un step `wait` suspende: `POST /run` devuelve `{run_id, status:"suspended"}`
   y el estado queda persistido con `current_index` apuntando al step posterior al `wait`.
2. `POST /runs/{id}/resume` continúa la corrida hasta completar, con el payload disponible en
   el `context`.
3. Un workflow sin `wait` devuelve el `WorkflowRunResult` completo por `POST /run` (fachada
   síncrona intacta).
4. Cargar la corrida desde el store en un proceso nuevo y resumir funciona (durabilidad real).
5. `sweep_expired` marca `expired` las esperas vencidas; `mark_orphaned_failed` marca `failed`
   las `running` al bootstrap.
6. `SqliteRunStore` persiste y recupera correctamente.
7. `pytest` verde y `ruff check` limpio.
