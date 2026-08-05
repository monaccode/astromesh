# Encadenamiento de agentes (`spec.chain`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que un agente declare en su propio YAML qué agentes disparar al terminar, condicionalmente, compilando esa declaración a un `WorkflowSpec` que el motor existente ejecuta.

**Architecture:** Azúcar declarativa (`spec.chain`) que un compilador traduce, en tiempo de bootstrap, a un `WorkflowSpec` sintético `__chain__<agente>` registrado en el `WorkflowEngine`. Las condiciones operan sobre `output.data`, un objeto estructurado que un `output_schema` nuevo puebla y valida. El motor recibe tres adiciones acotadas y de utilidad general: guarda `when` por paso, `on_error: continue`, y `StepType.PARALLEL`.

**Tech Stack:** Python 3.12+, `uv`, `pytest` (asyncio_mode auto), Jinja2, FastAPI, `respx` para HTTP, `asgi-lifespan` en `tests/conftest.py`.

**Spec:** `docs/superpowers/specs/2026-07-29-agent-chaining-design.md`

## Global Constraints

- **Cero dependencias de runtime nuevas.** Las deps base son `fastapi, uvicorn[standard], httpx, pydantic, pyyaml, jinja2, psutil`. `jsonschema` es dev-only y **no** se sube a base: `api.main` tiene que importar sin extras porque la imagen de `astromesh-os` la construye con pip.
- **Compatibilidad hacia atrás obligatoria.** Un agente sin `spec.chain` y sin `spec.output_schema` debe devolver de `POST /v1/agents/{n}/run` exactamente la misma forma que hoy. Un workflow escrito a mano sin `when`, sin `parallel` y sin `strict_conditions` debe comportarse exactamente igual que hoy.
- **Line length 100.** Target Python 3.12. Lint: `uv run ruff check astromesh/ tests/` y `uv run ruff format astromesh/ tests/`.
- **`asyncio_mode = "auto"`**: las funciones de test async no llevan decorador.
- **Commits convencionales**: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`.
- **Changelog obligatorio**: todo commit `feat:` o `fix:` necesita su entrada en `CHANGELOG.md` bajo `## [Unreleased]` en el mismo commit. Usar la skill `/changelog-automation`.
- **No bumpear versiones.** Este plan no hace release; no tocar `pyproject.toml`, `astromesh/__init__.py` ni lockfiles.
- **Comentarios en castellano** cuando expliquen una decisión no obvia, siguiendo el estilo del repo (ver `astromesh/workflow/executor.py`). Docstrings en inglés o castellano según el archivo vecino.

---

## Estructura de archivos

### Se crean

| archivo | responsabilidad |
|---|---|
| `astromesh/chain/__init__.py` | exporta `compile_chain`, `ChainSpec`, `ChainLink` |
| `astromesh/chain/validate.py` | validador mínimo de JSON Schema, sin dependencias |
| `astromesh/chain/output.py` | extrae y valida `data` desde la respuesta de un agente |
| `astromesh/chain/models.py` | `ChainSpec`, `ChainLink` — parseo del YAML |
| `astromesh/chain/compiler.py` | `compile_chain(...) -> WorkflowSpec` |

### Se modifican

| archivo | qué cambia |
|---|---|
| `astromesh/workflow/models.py` | `StepSpec.when`, `.strict_conditions`, `.parallel`; `StepType.PARALLEL`; `StepResult.condition_matched` |
| `astromesh/workflow/executor.py` | guarda `when`, `StrictUndefined`, `_run_parallel`, herencia de trace |
| `astromesh/workflow/__init__.py` | `_drive`: `SKIPPED`, `on_error: continue`, slot `when`, aplanado de paralelos |
| `astromesh/workflow/loader.py` | parsea `when`/`parallel`; rechaza el prefijo reservado `__chain__` |
| `astromesh/runtime/engine.py` | `output_schema` en `_build_agent` y `Agent.run`; compilación de cadenas en `bootstrap` |
| `astromesh/api/main.py` | instancia el `WorkflowEngine` en el lifespan |
| `astromesh/api/routes/agents.py` | `/run` con cadena; `GET /agents/{n}/chain` |
| `config/workflows/example.workflow.yaml` | arreglar el `when` roto |
| `config/agents/sales-qualifier.agent.yaml` | ejemplo con `output_schema` + `chain` |
| `CHANGELOG.md` | entradas bajo `[Unreleased]` |

---

## Task 1: Cablear el `WorkflowEngine` en el lifespan

Hoy `set_workflow_engine()` no se llama en producción: `/v1/workflows/` devuelve `[]` siempre y ningún workflow corre. Nada del resto del plan se puede probar end-to-end sin esto.

**Files:**
- Modify: `astromesh/api/main.py:62-120` (la función `lifespan`)
- Test: `tests/test_workflow_wiring.py` (crear)

**Interfaces:**
- Consumes: `WorkflowEngine(workflows_dir, runtime, tool_registry, store)` y `await engine.bootstrap()` de `astromesh/workflow/__init__.py`; `workflows.set_workflow_engine(engine)` de `astromesh/api/routes/workflows.py:17`.
- Produces: `app.state.workflow_engine` — el `WorkflowEngine` vivo, que las Tasks 11 y 12 usan.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_workflow_wiring.py`:

```python
"""El WorkflowEngine debe quedar instanciado y cableado por el lifespan."""

import os

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def workflows_config(tmp_path):
    """Un config_dir con un workflow mínimo en disco."""
    (tmp_path / "agents").mkdir()
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    (wf_dir / "ping.workflow.yaml").write_text(
        """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: ping
spec:
  description: "workflow de prueba"
  steps:
    - name: uno
      tool: noop
""",
        encoding="utf-8",
    )
    return tmp_path


async def test_lifespan_wires_workflow_engine(workflows_config, monkeypatch):
    monkeypatch.setenv("ASTROMESH_CONFIG_DIR", str(workflows_config))
    monkeypatch.delenv("ASTROMESH_SKIP_RUNTIME", raising=False)

    from astromesh.api.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/workflows/")

    assert resp.status_code == 200
    assert "ping" in resp.json()["workflows"], (
        "el lifespan no cableó el WorkflowEngine: /v1/workflows/ vino vacío"
    )


async def test_engine_survives_missing_workflows_dir(tmp_path, monkeypatch):
    """Un config_dir sin carpeta workflows/ no debe romper el arranque."""
    (tmp_path / "agents").mkdir()
    monkeypatch.setenv("ASTROMESH_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("ASTROMESH_SKIP_RUNTIME", raising=False)

    from astromesh.api.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/workflows/")

    assert resp.status_code == 200
    assert resp.json()["workflows"] == []
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
uv run pytest tests/test_workflow_wiring.py -v
```

Esperado: `test_lifespan_wires_workflow_engine` FALLA — `assert "ping" in []`, porque `_engine is None` y la ruta devuelve la lista vacía.

- [ ] **Step 3: Cablear el motor en el lifespan**

En `astromesh/api/main.py`, dentro de `lifespan`, **después** de `await runtime.bootstrap()` y de los `set_runtime(...)` (o sea después de la línea 110), agregar:

```python
    # El WorkflowEngine existía desde hace varias versiones pero nunca se instanciaba
    # fuera de los tests: `set_workflow_engine` no se llamaba desde acá, así que
    # /v1/workflows/ devolvía [] siempre y ningún workflow corría en producción.
    workflow_engine = None
    try:
        from astromesh.workflow import WorkflowEngine

        workflow_engine = WorkflowEngine(
            workflows_dir=str(Path(config_dir) / "workflows"),
            runtime=runtime,
            tool_registry=runtime.tools,
            store=None,  # InMemoryRunStore; el store durable se elige en Task 12
        )
        await workflow_engine.bootstrap()
        workflows_route.set_workflow_engine(workflow_engine)
        app.state.workflow_engine = workflow_engine
        logger.info(
            "WorkflowEngine listo: workflows_cargados=%d",
            len(workflow_engine.list_workflows()),
        )
    except Exception:
        # Un workflow mal escrito no puede impedir que arranque la API: los agentes
        # siguen sirviendo aunque el motor de workflows quede fuera.
        logger.exception("WorkflowEngine bootstrap falló (config_dir=%s)", config_dir)
```

En el bloque de teardown (junto a los `set_runtime(None)` de las líneas 115-120), agregar:

```python
        workflows_route.set_workflow_engine(None)
        app.state.workflow_engine = None
```

Asegurar los imports en el encabezado del módulo: `from pathlib import Path` y agregar `workflows as workflows_route` al import de rutas — verificar cómo está importado `workflows` hoy en la línea 27 y usar un alias si ya está importado con otro nombre.

- [ ] **Step 4: Correr los tests y verificar que pasan**

```bash
uv run pytest tests/test_workflow_wiring.py -v
uv run pytest tests/test_workflow_api.py tests/test_api.py -v
```

Esperado: todo PASS. Los tests existentes de `test_workflow_api.py` usan `set_workflow_engine` con un mock; verificar que no quedan contaminados por el motor real (usan la fixture propia, deberían estar bien — si alguno falla por orden de tests, agregar `set_workflow_engine(None)` en el teardown de su fixture).

- [ ] **Step 5: Lint y commit**

```bash
uv run ruff format astromesh/api/main.py tests/test_workflow_wiring.py
uv run ruff check astromesh/api/main.py tests/test_workflow_wiring.py
git add astromesh/api/main.py tests/test_workflow_wiring.py CHANGELOG.md
git commit -m "fix(api): instanciar el WorkflowEngine en el lifespan

El motor existía y estaba testeado, pero set_workflow_engine() nunca se
llamaba fuera de tests: /v1/workflows/ devolvía [] siempre y ningún
workflow corría en producción."
```

Antes de commitear, agregar a `CHANGELOG.md` bajo `## [Unreleased]` → `### Fixed`:

```markdown
- **Workflows**: el `WorkflowEngine` ahora se instancia en el lifespan de la API. Antes
  nunca se cableaba fuera de los tests, así que `/v1/workflows/` devolvía una lista vacía
  y ningún workflow definido en `config/workflows/` llegaba a ejecutarse.
```

---

## Task 2: Heredar trace y sesión en los pasos `agent`

`StepExecutor._run_agent` genera `session_id = str(uuid.uuid4())` por paso y no pasa `parent_trace_id`. Cada paso abre su propio árbol de trazas, así que un workflow (y más adelante una cadena) es invisible en el timeline.

**Files:**
- Modify: `astromesh/workflow/executor.py:25-31` (`__init__`), `:73-80` (`_run_agent`), `:33-57` (`execute_step`)
- Test: `tests/test_workflow_trace_inheritance.py` (crear)

**Interfaces:**
- Consumes: `AgentRuntime.run(agent_name, query, session_id, context=None, parent_trace_id=None, ...)` — la firma de `astromesh/runtime/engine.py:604`.
- Produces: `StepExecutor(runtime, tool_registry, parent_trace_id=None, session_id=None)` — las Tasks 8 y 10 dependen de esta firma.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_workflow_trace_inheritance.py`:

```python
"""Los pasos `agent` deben correr dentro del trace y la sesión del run."""

from astromesh.workflow.executor import StepExecutor
from astromesh.workflow.models import StepSpec


class _RuntimeSpy:
    """Registra con qué session_id y parent_trace_id se invocó cada agente."""

    def __init__(self):
        self.calls = []

    async def run(self, agent_name, query, session_id, context=None, parent_trace_id=None, **kw):
        self.calls.append(
            {
                "agent": agent_name,
                "query": query,
                "session_id": session_id,
                "parent_trace_id": parent_trace_id,
            }
        )
        return {"answer": f"respuesta de {agent_name}", "steps": []}


async def test_agent_step_inherits_trace_and_session():
    runtime = _RuntimeSpy()
    executor = StepExecutor(
        runtime=runtime,
        tool_registry=None,
        parent_trace_id="trace-abc",
        session_id="sesion-1",
    )
    step = StepSpec(name="uno", agent="analista", input_template="hola")

    await executor.execute_step(step, {})

    assert runtime.calls[0]["parent_trace_id"] == "trace-abc"
    assert runtime.calls[0]["session_id"] == "sesion-1"


async def test_all_steps_share_one_session():
    runtime = _RuntimeSpy()
    executor = StepExecutor(
        runtime=runtime,
        tool_registry=None,
        parent_trace_id="trace-abc",
        session_id="sesion-1",
    )

    await executor.execute_step(StepSpec(name="uno", agent="a", input_template="x"), {})
    await executor.execute_step(StepSpec(name="dos", agent="b", input_template="y"), {})

    sesiones = {c["session_id"] for c in runtime.calls}
    assert sesiones == {"sesion-1"}, f"cada paso abrió su propia sesión: {sesiones}"


async def test_falls_back_to_generated_session_when_not_given():
    """Sin session_id explícito se sigue generando uno: no rompe llamadas viejas."""
    runtime = _RuntimeSpy()
    executor = StepExecutor(runtime=runtime, tool_registry=None)

    await executor.execute_step(StepSpec(name="uno", agent="a", input_template="x"), {})

    assert runtime.calls[0]["session_id"]
    assert runtime.calls[0]["parent_trace_id"] is None
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
uv run pytest tests/test_workflow_trace_inheritance.py -v
```

Esperado: los dos primeros FALLAN con `TypeError: __init__() got an unexpected keyword argument 'parent_trace_id'`.

- [ ] **Step 3: Implementar**

En `astromesh/workflow/executor.py`, reemplazar `__init__`:

```python
    def __init__(self, runtime, tool_registry, parent_trace_id=None, session_id=None):
        self._runtime = runtime
        self._tool_registry = tool_registry
        self._jinja = Environment(loader=BaseLoader(), undefined=_SilentUndefined)
        # Hasta acá cada paso `agent` abría su propia sesión y su propio árbol de
        # trazas, así que un workflow se veía en el timeline como N corridas sueltas
        # sin relación entre sí.
        self._parent_trace_id = parent_trace_id
        self._session_id = session_id
```

y reemplazar `_run_agent`:

```python
    async def _run_agent(self, step: StepSpec, ctx: dict, start: float) -> StepResult:
        rendered_input = self._render(step.input_template or "", ctx)
        session_id = self._session_id or str(uuid.uuid4())
        result = await self._runtime.run(
            step.agent,
            rendered_input,
            session_id=session_id,
            parent_trace_id=self._parent_trace_id,
        )
        elapsed = (time.time() - start) * 1000
        return StepResult(
            name=step.name, status=StepStatus.SUCCESS, output=result, duration_ms=elapsed
        )
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

```bash
uv run pytest tests/test_workflow_trace_inheritance.py -v
uv run pytest tests/ -k workflow -v
```

Esperado: todo PASS.

- [ ] **Step 5: Pasar el trace del run al executor**

En `astromesh/workflow/__init__.py`, dentro de `_drive`, después de crear el `TracingContext` y el `root_span`, el executor compartido (`self._executor`) no tiene el trace del run. Reemplazar el uso de `self._executor` dentro de `_drive` por un executor por-run:

```python
        # Un executor por corrida: lleva el trace_id y la sesión del run, para que
        # todos los pasos cuelguen del mismo árbol.
        executor = StepExecutor(
            runtime=self._runtime,
            tool_registry=self._tool_registry,
            parent_trace_id=tracing.trace_id,
            session_id=run.run_id,
        )
```

y cambiar las **dos** llamadas `await self._executor.execute_step(...)` de `_drive` (la del bucle principal y la del `goto`) por `await executor.execute_step(...)`.

Agregar el import: `from astromesh.workflow.executor import StepExecutor` ya está en el encabezado del módulo.

- [ ] **Step 6: Correr toda la suite de workflow**

```bash
uv run pytest tests/ -k "workflow or chain" -v
```

Esperado: todo PASS. Si algún test mockea `engine._executor`, ajustarlo para mockear `StepExecutor` en el módulo.

- [ ] **Step 7: Lint y commit**

```bash
uv run ruff format astromesh/workflow/ tests/test_workflow_trace_inheritance.py
uv run ruff check astromesh/workflow/ tests/test_workflow_trace_inheritance.py
git add astromesh/workflow/ tests/test_workflow_trace_inheritance.py CHANGELOG.md
git commit -m "fix(workflow): los pasos agent heredan trace y sesión del run

_run_agent generaba una sesión nueva por paso y no propagaba
parent_trace_id, así que cada paso abría su propio árbol de trazas y el
workflow era invisible como unidad en el timeline."
```

Entrada de `CHANGELOG.md` bajo `### Fixed`:

```markdown
- **Workflows**: los pasos de tipo `agent` ahora heredan el `trace_id` y la sesión de la
  corrida. Antes cada paso generaba una sesión nueva y no propagaba `parent_trace_id`, así
  que un workflow aparecía en el timeline como corridas sueltas sin relación.
```

---

## Task 3: Validador mínimo de JSON Schema

**Files:**
- Create: `astromesh/chain/__init__.py`, `astromesh/chain/validate.py`
- Test: `tests/test_chain_validate.py` (crear)

**Interfaces:**
- Produces: `validate(data: Any, schema: dict) -> list[str]` — devuelve lista de mensajes de error; vacía significa válido. Lo usan las Tasks 4 y 5.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_chain_validate.py`:

```python
"""Validador mínimo de JSON Schema, sin dependencias externas."""

from astromesh.chain.validate import validate


def test_objeto_valido_no_da_errores():
    schema = {
        "type": "object",
        "properties": {"score": {"type": "integer"}, "urgent": {"type": "boolean"}},
        "required": ["score"],
    }
    assert validate({"score": 8, "urgent": True}, schema) == []


def test_campo_requerido_faltante():
    schema = {"type": "object", "properties": {"score": {"type": "integer"}}, "required": ["score"]}
    errores = validate({}, schema)
    assert len(errores) == 1
    assert "score" in errores[0]


def test_tipo_incorrecto():
    schema = {"type": "object", "properties": {"score": {"type": "integer"}}}
    errores = validate({"score": "ocho"}, schema)
    assert len(errores) == 1
    assert "score" in errores[0] and "integer" in errores[0]


def test_bool_no_es_integer():
    """En Python bool es subclase de int; el validador no debe dejarlo pasar."""
    schema = {"type": "object", "properties": {"score": {"type": "integer"}}}
    assert validate({"score": True}, schema) != []


def test_integer_es_number_valido():
    schema = {"type": "object", "properties": {"ratio": {"type": "number"}}}
    assert validate({"ratio": 3}, schema) == []


def test_enum():
    schema = {"type": "object", "properties": {"tier": {"type": "string", "enum": ["a", "b"]}}}
    assert validate({"tier": "a"}, schema) == []
    assert validate({"tier": "z"}, schema) != []


def test_array_con_items():
    schema = {
        "type": "object",
        "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
    }
    assert validate({"tags": ["x", "y"]}, schema) == []
    errores = validate({"tags": ["x", 3]}, schema)
    assert len(errores) == 1
    assert "tags[1]" in errores[0]


def test_objeto_anidado():
    schema = {
        "type": "object",
        "properties": {
            "lead": {
                "type": "object",
                "properties": {"score": {"type": "integer"}},
                "required": ["score"],
            }
        },
    }
    assert validate({"lead": {"score": 8}}, schema) == []
    errores = validate({"lead": {}}, schema)
    assert "lead.score" in errores[0]


def test_null_permitido():
    schema = {"type": "object", "properties": {"nota": {"type": "null"}}}
    assert validate({"nota": None}, schema) == []


def test_raiz_no_es_objeto():
    schema = {"type": "object", "properties": {}}
    errores = validate(["no", "soy", "objeto"], schema)
    assert len(errores) == 1


def test_keywords_no_soportadas_se_ignoran():
    """oneOf/allOf/format/minimum se ignoran: no rompen, no validan."""
    schema = {
        "type": "object",
        "properties": {"score": {"type": "integer", "minimum": 10, "format": "int32"}},
        "oneOf": [{"required": ["score"]}],
    }
    assert validate({"score": 3}, schema) == []


def test_propiedad_extra_se_permite():
    schema = {"type": "object", "properties": {"score": {"type": "integer"}}}
    assert validate({"score": 8, "extra": "libre"}, schema) == []


def test_varios_errores_a_la_vez():
    schema = {
        "type": "object",
        "properties": {"a": {"type": "integer"}, "b": {"type": "string"}},
        "required": ["a", "b", "c"],
    }
    errores = validate({"a": "no", "b": 3}, schema)
    assert len(errores) == 3  # a mal tipo, b mal tipo, c faltante
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
uv run pytest tests/test_chain_validate.py -v
```

Esperado: FALLA con `ModuleNotFoundError: No module named 'astromesh.chain'`.

- [ ] **Step 3: Implementar**

Crear `astromesh/chain/__init__.py`:

```python
"""Encadenamiento declarativo de agentes (`spec.chain`)."""
```

Crear `astromesh/chain/validate.py`:

```python
"""Validador mínimo de JSON Schema para `spec.output_schema`.

Deliberadamente no usa `jsonschema`: esa librería es dependencia de dev
únicamente, y subirla a las deps base obligaría a re-lockear tres proyectos uv
y agregaría una dependencia al arranque de la imagen de astromesh-os (que se
construye con pip). El subconjunto de abajo cubre lo que un `output_schema` de
agente usa de verdad.

Soporta: type (object, string, integer, number, boolean, array, null),
properties, required, enum, items.

Ignora, a propósito y sin avisar: allOf, anyOf, oneOf, not, $ref,
patternProperties, additionalProperties, format, minimum, maximum, minLength,
maxLength, pattern, minItems, maxItems, uniqueItems.

Ignorar en vez de rechazar es deliberado: un output_schema con `oneOf` sigue
validando las partes que este módulo entiende, en lugar de tumbar el agente
entero por una keyword que no conocemos.
"""

from __future__ import annotations

from typing import Any

# bool antes que int a propósito: en Python `isinstance(True, int)` es True, y
# un `{"type": "integer"}` que acepte `true` es un agujero silencioso en las
# condiciones de una cadena.
_CHECKS = {
    "null": lambda v: v is None,
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "string": lambda v: isinstance(v, str),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def validate(data: Any, schema: dict | None) -> list[str]:
    """Valida `data` contra `schema`. Devuelve los errores; lista vacía = válido."""
    if not schema:
        return []
    return _validate(data, schema, path="")


def _validate(value: Any, schema: dict, path: str) -> list[str]:
    errors: list[str] = []
    label = path or "(raíz)"

    expected = schema.get("type")
    if expected:
        check = _CHECKS.get(expected)
        if check is not None and not check(value):
            return [f"{label}: se esperaba {expected}, llegó {type(value).__name__}"]

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        errors.append(f"{label}: {value!r} no está en enum {enum}")

    if expected == "object" or (expected is None and isinstance(value, dict)):
        errors.extend(_validate_object(value, schema, path))
    elif expected == "array" or (expected is None and isinstance(value, list)):
        errors.extend(_validate_array(value, schema, path))

    return errors


def _validate_object(value: Any, schema: dict, path: str) -> list[str]:
    if not isinstance(value, dict):
        return []
    errors: list[str] = []
    prefix = f"{path}." if path else ""

    for name in schema.get("required", []):
        if name not in value:
            errors.append(f"{prefix}{name}: campo requerido faltante")

    for name, subschema in (schema.get("properties") or {}).items():
        if name in value and isinstance(subschema, dict):
            errors.extend(_validate(value[name], subschema, f"{prefix}{name}"))

    return errors


def _validate_array(value: Any, schema: dict, path: str) -> list[str]:
    if not isinstance(value, list):
        return []
    items = schema.get("items")
    if not isinstance(items, dict):
        return []
    errors: list[str] = []
    label = path or "(raíz)"
    for i, item in enumerate(value):
        errors.extend(_validate(item, items, f"{label}[{i}]"))
    return errors
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

```bash
uv run pytest tests/test_chain_validate.py -v
```

Esperado: 13 PASS.

- [ ] **Step 5: Lint y commit**

```bash
uv run ruff format astromesh/chain/ tests/test_chain_validate.py
uv run ruff check astromesh/chain/ tests/test_chain_validate.py
git add astromesh/chain/ tests/test_chain_validate.py
git commit -m "test: validador mínimo de JSON Schema para output_schema"
```

(Commit `test:`, no `feat:` — todavía no lo usa nadie, así que no hay entrada de changelog.)

---

## Task 4: Extracción de `data` desde la respuesta del agente

**Files:**
- Create: `astromesh/chain/output.py`
- Test: `tests/test_chain_output_extract.py` (crear)

**Interfaces:**
- Consumes: `validate(data, schema) -> list[str]` de la Task 3; `normalize_tool_parameters(parameters) -> dict | None` de `astromesh/core/schema.py:18`.
- Produces:
  - `normalize_output_schema(raw: dict | None) -> dict | None`
  - `extract_data(answer: str) -> Any | None`
  - `build_data(answer: str, schema: dict | None) -> tuple[Any | None, str | None]` — devuelve `(data, data_error)`. La Task 5 la usa.
  - `schema_prompt_block(schema: dict) -> str`

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_chain_output_extract.py`:

```python
"""Extracción y validación de `data` desde la respuesta en prosa de un agente."""

from astromesh.chain.output import (
    build_data,
    extract_data,
    normalize_output_schema,
    schema_prompt_block,
)

SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "integer"}, "urgent": {"type": "boolean"}},
    "required": ["score"],
}


def test_normaliza_taquigrafia():
    """La misma taquigrafía que usan los `parameters` de las tools."""
    normalizado = normalize_output_schema({"score": {"type": "integer"}})
    assert normalizado == {"type": "object", "properties": {"score": {"type": "integer"}}}


def test_json_schema_completo_pasa_intacto():
    assert normalize_output_schema(SCHEMA) == SCHEMA


def test_none_pasa_como_none():
    assert normalize_output_schema(None) is None


def test_extrae_bloque_json_cercado():
    answer = 'Analicé el lead.\n\n```json\n{"score": 8, "urgent": true}\n```\n\nRecomiendo contactar.'
    assert extract_data(answer) == {"score": 8, "urgent": True}


def test_usa_el_ultimo_bloque_json():
    """Si el modelo razonó con un borrador antes, vale el último."""
    answer = '```json\n{"score": 1}\n```\ncorrijo:\n```json\n{"score": 9}\n```'
    assert extract_data(answer) == {"score": 9}


def test_bloque_cercado_sin_etiqueta_de_lenguaje():
    answer = 'listo:\n```\n{"score": 5}\n```'
    assert extract_data(answer) == {"score": 5}


def test_respuesta_entera_es_json_pelado():
    assert extract_data('{"score": 7}') == {"score": 7}


def test_sin_json_devuelve_none():
    assert extract_data("No pude determinar el score.") is None


def test_json_invalido_devuelve_none():
    assert extract_data('```json\n{"score": no-soy-json}\n```') is None


def test_build_data_camino_feliz():
    answer = 'Calificado.\n```json\n{"score": 8, "urgent": true}\n```'
    data, error = build_data(answer, SCHEMA)
    assert data == {"score": 8, "urgent": True}
    assert error is None


def test_build_data_sin_schema_no_hace_nada():
    data, error = build_data('```json\n{"score": 8}\n```', None)
    assert data is None
    assert error is None


def test_build_data_sin_bloque_json():
    data, error = build_data("Prosa sin JSON.", SCHEMA)
    assert data is None
    assert "no se encontró" in error


def test_build_data_falla_validacion():
    answer = '```json\n{"urgent": true}\n```'
    data, error = build_data(answer, SCHEMA)
    assert data is None
    assert "score" in error


def test_prompt_block_menciona_los_campos():
    bloque = schema_prompt_block(SCHEMA)
    assert "score" in bloque
    assert "json" in bloque.lower()
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
uv run pytest tests/test_chain_output_extract.py -v
```

Esperado: FALLA con `ModuleNotFoundError: No module named 'astromesh.chain.output'`.

- [ ] **Step 3: Implementar**

Crear `astromesh/chain/output.py`:

```python
"""Salida estructurada de un agente: `spec.output_schema` -> `result["data"]`.

Ningún provider del repo soporta `response_format` ni `json_schema` nativo, así
que la forma se pide por prompt y se parsea de la respuesta. `answer` nunca se
toca: `data` se agrega al lado, así que quien hoy lee `answer` no se entera.
"""

from __future__ import annotations

import json
import re
from typing import Any

from astromesh.chain.validate import validate
from astromesh.core.schema import normalize_tool_parameters

# ```json ... ``` o ``` ... ```; no-greedy y multilínea.
_FENCED = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.DOTALL)


def normalize_output_schema(raw: dict | None) -> dict | None:
    """Acepta la misma taquigrafía YAML que los `parameters` de las tools."""
    return normalize_tool_parameters(raw)


def extract_data(answer: str) -> Any | None:
    """Saca el objeto JSON de una respuesta en prosa. None si no hay o no parsea."""
    if not answer:
        return None

    # El último bloque gana: si el modelo mostró un borrador y después lo
    # corrigió, la corrección es la que vale.
    for bloque in reversed(_FENCED.findall(answer)):
        try:
            return json.loads(bloque)
        except json.JSONDecodeError:
            continue

    try:
        return json.loads(answer.strip())
    except json.JSONDecodeError:
        return None


def build_data(answer: str, schema: dict | None) -> tuple[Any | None, str | None]:
    """Devuelve (data, data_error). Sin schema, ambos None y no se hace nada.

    Un fallo de validación NO levanta excepción: deja data en None y describe el
    problema en data_error. Cortar la corrida del agente porque el modelo escribió
    mal un JSON sería peor que devolver la prosa, que casi siempre sigue sirviendo.
    """
    if not schema:
        return None, None

    data = extract_data(answer)
    if data is None:
        return None, "no se encontró un objeto JSON válido en la respuesta"

    errores = validate(data, schema)
    if errores:
        return None, "; ".join(errores)

    return data, None


def schema_prompt_block(schema: dict) -> str:
    """Instrucción que se anexa al system prompt para pedir la salida estructurada."""
    return (
        "\n\n## Salida estructurada (obligatorio)\n"
        "Respondé normalmente en prosa y, al final, agregá un bloque de código "
        "etiquetado `json` con un objeto que cumpla exactamente este JSON Schema:\n\n"
        "```json\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "El bloque debe ser el último de tu respuesta y contener sólo el objeto JSON."
    )
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

```bash
uv run pytest tests/test_chain_output_extract.py -v
```

Esperado: 14 PASS.

- [ ] **Step 5: Lint y commit**

```bash
uv run ruff format astromesh/chain/ tests/test_chain_output_extract.py
uv run ruff check astromesh/chain/ tests/test_chain_output_extract.py
git add astromesh/chain/output.py tests/test_chain_output_extract.py
git commit -m "test: extracción y validación de data desde la respuesta del agente"
```

---

## Task 5: `output_schema` en el agente

**Files:**
- Modify: `astromesh/runtime/engine.py` — `_build_agent` (cerca de `:595-602`), `Agent.__init__` (`:760-772`), `Agent.run` (el bloque de `rendered_prompt` en `:815-822` y el `return result` en `:997-1004`)
- Test: `tests/test_chain_output_schema.py` (crear)

**Interfaces:**
- Consumes: `normalize_output_schema`, `build_data`, `schema_prompt_block` de la Task 4.
- Produces: `agent.run()` devuelve `data` y `data_error` en el dict de resultado cuando el agente declara `output_schema`. Las Tasks 10 y 12 dependen de esto.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_chain_output_schema.py`:

```python
"""Un agente con spec.output_schema devuelve `data` validada junto a `answer`."""

import pytest

from astromesh.runtime.engine import AgentRuntime

AGENTE_CON_SCHEMA = """
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: calificador
spec:
  identity:
    description: "califica leads"
  model:
    primary:
      provider: ollama
      model: "test"
      endpoint: "http://localhost:11434"
  prompts:
    system: "Sos un calificador."
  output_schema:
    score:  {type: integer}
    urgent: {type: boolean}
  orchestration:
    pattern: react
    max_iterations: 1
"""

AGENTE_SIN_SCHEMA = AGENTE_CON_SCHEMA.replace(
    "  output_schema:\n    score:  {type: integer}\n    urgent: {type: boolean}\n", ""
).replace("name: calificador", "name: simple")


@pytest.fixture
def config_dir(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "calificador.agent.yaml").write_text(AGENTE_CON_SCHEMA, encoding="utf-8")
    (agents / "simple.agent.yaml").write_text(AGENTE_SIN_SCHEMA, encoding="utf-8")
    return tmp_path


async def _run_con_respuesta(runtime, agente, respuesta, monkeypatch):
    """Fuerza al patrón de orquestación a devolver `respuesta` como answer."""

    async def fake_execute(query, context, model_fn, tool_fn, tools, max_iterations=10):
        return {"answer": respuesta, "steps": []}

    monkeypatch.setattr(runtime._agents[agente]._pattern, "execute", fake_execute)
    return await runtime.run(agente, "un lead", session_id="s1")


async def test_data_poblada_y_validada(config_dir, monkeypatch):
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()

    result = await _run_con_respuesta(
        runtime,
        "calificador",
        'Buen lead.\n```json\n{"score": 8, "urgent": true}\n```',
        monkeypatch,
    )

    assert result["data"] == {"score": 8, "urgent": True}
    assert result["data_error"] is None
    assert result["answer"].startswith("Buen lead."), "answer debe quedar intacta, con prosa"


async def test_json_faltante_no_rompe_la_corrida(config_dir, monkeypatch):
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()

    result = await _run_con_respuesta(runtime, "calificador", "No pude calificarlo.", monkeypatch)

    assert result["data"] is None
    assert "no se encontró" in result["data_error"]
    assert result["answer"] == "No pude calificarlo."


async def test_validacion_fallida_no_rompe_la_corrida(config_dir, monkeypatch):
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()

    result = await _run_con_respuesta(
        runtime, "calificador", '```json\n{"score": "ocho"}\n```', monkeypatch
    )

    assert result["data"] is None
    assert "score" in result["data_error"]


async def test_agente_sin_schema_no_gana_claves(config_dir, monkeypatch):
    """Guarda de regresión: la forma del resultado no cambia para quien no opta."""
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()

    result = await _run_con_respuesta(runtime, "simple", '```json\n{"score": 8}\n```', monkeypatch)

    assert "data" not in result
    assert "data_error" not in result


async def test_el_schema_llega_al_system_prompt(config_dir, monkeypatch):
    """El modelo tiene que enterarse de la forma pedida: ningún provider soporta
    response_format, así que la instrucción va por prompt."""
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    capturado = {}

    class _Respuesta:
        content = '```json\n{"score": 5}\n```'
        tool_calls = None
        model = "test"
        provider = "test"
        latency_ms = 1
        cost = 0.0
        usage = None

    async def fake_execute(query, context, model_fn, tool_fn, tools, max_iterations=10):
        # model_fn antepone el system prompt ya renderizado a los mensajes.
        resp = await model_fn([{"role": "user", "content": "x"}], [])
        return {"answer": resp.content, "steps": []}

    agente = runtime._agents["calificador"]

    async def spy_route(messages, tools=None, **kw):
        capturado["system"] = messages[0]["content"]
        return _Respuesta()

    monkeypatch.setattr(agente._pattern, "execute", fake_execute)
    monkeypatch.setattr(agente._routers["default"], "route", spy_route)

    await runtime.run("calificador", "un lead", session_id="s1")

    assert "score" in capturado["system"]
    assert "json" in capturado["system"].lower()
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
uv run pytest tests/test_chain_output_schema.py -v
```

Esperado: FALLA con `KeyError: 'data'`.

- [ ] **Step 3: Implementar — leer el schema en `_build_agent`**

En `astromesh/runtime/engine.py`, en `_build_agent`, dentro de la construcción del `Agent(...)` (alrededor de la línea 595), agregar el argumento:

```python
            output_schema=normalize_output_schema(spec.get("output_schema")),
```

y en el encabezado del módulo agregar:

```python
from astromesh.chain.output import build_data, normalize_output_schema, schema_prompt_block
```

- [ ] **Step 4: Aceptarlo en `Agent.__init__`**

Agregar `output_schema=None` a la firma de `Agent.__init__` y, junto a las otras asignaciones (cerca de la línea 772):

```python
        self._output_schema = output_schema
```

- [ ] **Step 5: Inyectarlo en el prompt y poblar `data` en `Agent.run`**

En `Agent.run`, después de `rendered_prompt = self._prompt_engine.render(...)` y antes de `tracing.finish_span(prompt_span)`:

```python
            if self._output_schema:
                # Ningún provider del repo soporta response_format/json_schema, así
                # que la forma se pide por prompt y se parsea de la respuesta.
                rendered_prompt += schema_prompt_block(self._output_schema)
```

Y en el bloque final, justo antes de `result["trace"] = tracing.to_dict()`:

```python
            if self._output_schema:
                data, data_error = build_data(result.get("answer", ""), self._output_schema)
                result["data"] = data
                result["data_error"] = data_error
                root_span.set_attribute("output_data_ok", data_error is None)
                if data_error:
                    root_span.set_attribute("output_data_error", data_error)
```

Las claves se agregan **sólo** si el agente declara schema: un agente que no opta devuelve exactamente la misma forma que hoy.

- [ ] **Step 6: Correr los tests y verificar que pasan**

```bash
uv run pytest tests/test_chain_output_schema.py -v
uv run pytest tests/ -k "runtime or engine or agent" -v
```

Esperado: todo PASS.

- [ ] **Step 7: Lint y commit**

```bash
uv run ruff format astromesh/ tests/test_chain_output_schema.py
uv run ruff check astromesh/ tests/test_chain_output_schema.py
git add astromesh/runtime/engine.py tests/test_chain_output_schema.py CHANGELOG.md
git commit -m "feat(runtime): spec.output_schema devuelve data estructurada y validada"
```

Entrada de `CHANGELOG.md` bajo `### Added (Backend)`:

```markdown
- **Agentes**: nuevo `spec.output_schema` — el agente declara la forma de su salida y el
  runtime la parsea y valida en `result["data"]`, junto a la `answer` en prosa que queda
  intacta. Acepta la misma taquigrafía YAML que los `parameters` de las tools. Un fallo de
  validación no corta la corrida: deja `data` en `None` y describe el problema en
  `data_error`.
```

---

## Task 6: Guarda `when` por paso

`switch` + `goto` no sirve para "disparan todos los que matcheen": en `_drive`, el `goto` ejecuta el destino y corta el workflow. La guarda `when` es más chica, más general y le sirve a cualquier workflow escrito a mano.

**Files:**
- Modify: `astromesh/workflow/models.py:33-74` (`StepSpec`), `:77-84` (`StepResult`)
- Modify: `astromesh/workflow/executor.py:33-57` (`execute_step`), `:95-109` (`_run_switch`)
- Modify: `astromesh/workflow/__init__.py` — el bucle de `_drive`
- Modify: `astromesh/workflow/loader.py:57-73` (`_parse_step`)
- Test: `tests/test_workflow_when_guard.py` (crear)

**Interfaces:**
- Produces:
  - `StepSpec(..., when: str | None = None, strict_conditions: bool = False)`
  - `StepResult(..., condition_matched: bool | None = None)`
  - contexto `when` — `context["when"][<nombre de paso>] = bool` para cada paso con guarda. La Task 10 lo usa para compilar la regla `default`.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_workflow_when_guard.py`:

```python
"""Guarda `when` por paso: si no matchea, el paso queda SKIPPED y el run sigue."""

from astromesh.workflow.executor import StepExecutor
from astromesh.workflow.models import StepSpec, StepStatus


class _RuntimeSpy:
    def __init__(self):
        self.llamados = []

    async def run(self, agent_name, query, session_id, context=None, parent_trace_id=None, **kw):
        self.llamados.append(agent_name)
        return {"answer": f"ok {agent_name}", "steps": []}


def _executor(runtime):
    return StepExecutor(runtime=runtime, tool_registry=None)


async def test_guarda_verdadera_ejecuta_el_paso():
    runtime = _RuntimeSpy()
    step = StepSpec(name="uno", agent="a", input_template="x", when="{{ score > 7 }}")

    result = await _executor(runtime).execute_step(step, {"score": 9})

    assert result.status == StepStatus.SUCCESS
    assert result.condition_matched is True
    assert runtime.llamados == ["a"]


async def test_guarda_falsa_saltea_el_paso():
    runtime = _RuntimeSpy()
    step = StepSpec(name="uno", agent="a", input_template="x", when="{{ score > 7 }}")

    result = await _executor(runtime).execute_step(step, {"score": 2})

    assert result.status == StepStatus.SKIPPED
    assert result.condition_matched is False
    assert runtime.llamados == [], "el agente no debía ejecutarse"


async def test_sin_guarda_se_ejecuta_siempre():
    runtime = _RuntimeSpy()
    step = StepSpec(name="uno", agent="a", input_template="x")

    result = await _executor(runtime).execute_step(step, {})

    assert result.status == StepStatus.SUCCESS
    assert result.condition_matched is None
    assert runtime.llamados == ["a"]


async def test_guarda_acepta_yes_y_1():
    runtime = _RuntimeSpy()
    for expr in ("{{ 'yes' }}", "{{ 1 }}", "{{ true }}"):
        result = await _executor(runtime).execute_step(
            StepSpec(name="n", agent="a", input_template="x", when=expr), {}
        )
        assert result.status == StepStatus.SUCCESS, f"{expr} debía matchear"


async def test_guarda_no_estricta_con_campo_inexistente_da_falso():
    """Comportamiento histórico para workflows escritos a mano: silencio."""
    runtime = _RuntimeSpy()
    step = StepSpec(name="uno", agent="a", input_template="x", when="{{ nada.de.nada > 7 }}")

    result = await _executor(runtime).execute_step(step, {})

    assert result.status == StepStatus.SKIPPED
    assert runtime.llamados == []


async def test_guarda_estricta_con_campo_inexistente_da_error():
    runtime = _RuntimeSpy()
    step = StepSpec(
        name="uno",
        agent="a",
        input_template="x",
        when="{{ output.data.score > 7 }}",
        strict_conditions=True,
    )

    result = await _executor(runtime).execute_step(step, {})

    assert result.status == StepStatus.ERROR
    assert "uno" in result.error
    assert runtime.llamados == []


async def test_drive_publica_el_resultado_de_la_guarda_en_contexto():
    from astromesh.workflow import WorkflowEngine
    from astromesh.workflow.models import WorkflowSpec

    engine = WorkflowEngine(workflows_dir="", runtime=_RuntimeSpy(), tool_registry=None)
    await engine.bootstrap()
    engine.register_workflow(
        WorkflowSpec(
            name="wf",
            steps=[
                StepSpec(name="alto", agent="a", input_template="x", when="{{ trigger.n > 7 }}"),
                StepSpec(name="bajo", agent="b", input_template="x", when="{{ trigger.n <= 7 }}"),
            ],
        )
    )

    result = await engine.run("wf", trigger={"n": 9})

    assert result.status == "completed"
    assert result.steps["alto"].status == StepStatus.SUCCESS
    assert result.steps["bajo"].status == StepStatus.SKIPPED


async def test_un_paso_salteado_no_corta_el_run():
    from astromesh.workflow import WorkflowEngine
    from astromesh.workflow.models import WorkflowSpec

    runtime = _RuntimeSpy()
    engine = WorkflowEngine(workflows_dir="", runtime=runtime, tool_registry=None)
    await engine.bootstrap()
    engine.register_workflow(
        WorkflowSpec(
            name="wf",
            steps=[
                StepSpec(name="salteado", agent="a", input_template="x", when="{{ false }}"),
                StepSpec(name="corre", agent="b", input_template="x"),
            ],
        )
    )

    result = await engine.run("wf", trigger={})

    assert result.status == "completed"
    assert "b" in runtime.llamados, "el paso siguiente al salteado tenía que correr"
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
uv run pytest tests/test_workflow_when_guard.py -v
```

Esperado: FALLA con `TypeError: __init__() got an unexpected keyword argument 'when'`.

- [ ] **Step 3: Agregar los campos a los modelos**

En `astromesh/workflow/models.py`, dentro de `StepSpec`, agregar antes de `def __post_init__`:

```python
    when: str | None = None
    strict_conditions: bool = False
```

En `StepResult`, agregar:

```python
    condition_matched: bool | None = None
```

- [ ] **Step 4: Evaluar la guarda en el executor**

En `astromesh/workflow/executor.py`, agregar al import de jinja2 `StrictUndefined` y `UndefinedError`:

```python
from jinja2 import BaseLoader, Environment, StrictUndefined, Undefined
from jinja2.exceptions import UndefinedError
```

En `__init__`, junto al `self._jinja` existente:

```python
        # Entorno estricto para las guardas que lo pidan: un `when` con un campo
        # inexistente tiene que gritar, no rendir vacío y saltear en silencio.
        self._jinja_strict = Environment(loader=BaseLoader(), undefined=StrictUndefined)
```

Al principio de `execute_step`, antes del bucle de reintentos:

```python
        if step.when is not None:
            try:
                matched = self._eval_condition(step.when, context, step.strict_conditions)
            except UndefinedError as exc:
                return StepResult(
                    name=step.name,
                    status=StepStatus.ERROR,
                    error=f"condición inválida en el paso '{step.name}': {exc}",
                    condition_matched=False,
                )
            if not matched:
                return StepResult(
                    name=step.name, status=StepStatus.SKIPPED, condition_matched=False
                )
```

Y hay que propagar `condition_matched=True` al resultado del despacho. En el bucle de reintentos, reemplazar el bloque

```python
                coro = self._dispatch(step, context)
                if step.timeout_seconds:
                    result = await asyncio.wait_for(coro, timeout=step.timeout_seconds)
                else:
                    result = await coro
                return result
```

por

```python
                coro = self._dispatch(step, context)
                if step.timeout_seconds:
                    result = await asyncio.wait_for(coro, timeout=step.timeout_seconds)
                else:
                    result = await coro
                if step.when is not None:
                    result.condition_matched = True
                return result
```

Y en el `return StepResult(...)` final del método (el de error tras agotar reintentos), agregar el argumento:

```python
        return StepResult(
            name=step.name,
            status=StepStatus.ERROR,
            error=last_error,
            condition_matched=True if step.when is not None else None,
        )
```

Agregar el método:

```python
    def _eval_condition(self, expr: str, context: dict, strict: bool) -> bool:
        env = self._jinja_strict if strict else self._jinja
        rendered = env.from_string(expr).render(**context).strip()
        return rendered.lower() in ("true", "1", "yes")
```

Refactorizar `_run_switch` para que use `_eval_condition` en vez de duplicar el criterio:

```python
            condition = branch.get("when", "")
            if self._eval_condition(condition, ctx, step.strict_conditions):
                goto = branch["goto"]
                break
```

- [ ] **Step 5: Manejar `SKIPPED` y el slot `when` en `_drive`**

En `astromesh/workflow/__init__.py`, dentro del bucle `while i < len(wf.steps):` de `_drive`, justo después de `step_results[step.name] = result` y **antes** del chequeo de `SUSPENDED`:

```python
                if result.condition_matched is not None:
                    # Slot dedicado: el compilador de cadenas lo lee para armar la
                    # regla `default` (dispara sólo si ningún `when` matcheó).
                    context.setdefault("when", {})[step.name] = result.condition_matched

                if result.status == WfStepStatus.SKIPPED:
                    tracing.finish_span(step_span)
                    context["steps"][step.name] = {"output": None, "skipped": True}
                    run.current_index = i + 1
                    run.updated_at = datetime.now(UTC).isoformat()
                    await self._store.save(run)
                    i += 1
                    continue
```

- [ ] **Step 6: Parsear los campos nuevos en el loader**

En `astromesh/workflow/loader.py`, en `_parse_step`, agregar al `StepSpec(...)`:

```python
            when=raw.get("when"),
            strict_conditions=raw.get("strict_conditions", False),
```

- [ ] **Step 7: Correr los tests y verificar que pasan**

```bash
uv run pytest tests/test_workflow_when_guard.py -v
uv run pytest tests/ -k workflow -v
```

Esperado: todo PASS. Los workflows sin `when` no cambian de comportamiento (`condition_matched is None`, nunca se saltea).

- [ ] **Step 8: Lint y commit**

```bash
uv run ruff format astromesh/workflow/ tests/test_workflow_when_guard.py
uv run ruff check astromesh/workflow/ tests/test_workflow_when_guard.py
git add astromesh/workflow/ tests/test_workflow_when_guard.py CHANGELOG.md
git commit -m "feat(workflow): guarda when por paso con estado SKIPPED"
```

Entrada de `CHANGELOG.md` bajo `### Added (Backend)`:

```markdown
- **Workflows**: los pasos aceptan `when` — una condición Jinja que, si da falso, deja el
  paso en `skipped` y sigue con el resto. A diferencia de `switch` + `goto` (que ejecuta una
  rama y termina el workflow), permite que varios pasos condicionales convivan en una misma
  corrida. Con `strict_conditions: true` una condición que referencia un campo inexistente
  falla el paso en vez de evaluarse como falsa en silencio.
```

---

## Task 7: `on_error: continue`

**Files:**
- Modify: `astromesh/workflow/__init__.py` — el bloque `if result.status == WfStepStatus.ERROR:` de `_drive`
- Test: `tests/test_workflow_on_error_continue.py` (crear)

**Interfaces:**
- Produces: `on_error: "continue"` como valor reservado de `StepSpec.on_error`. La Task 10 lo emite.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_workflow_on_error_continue.py`:

```python
"""on_error: continue registra el fallo y sigue; el default sigue cortando."""

from astromesh.workflow import WorkflowEngine
from astromesh.workflow.models import StepSpec, StepStatus, WorkflowSpec


class _RuntimeQueRompe:
    """Falla para los agentes en `rotos`, responde bien para el resto."""

    def __init__(self, rotos):
        self._rotos = rotos
        self.llamados = []

    async def run(self, agent_name, query, session_id, context=None, parent_trace_id=None, **kw):
        self.llamados.append(agent_name)
        if agent_name in self._rotos:
            raise RuntimeError(f"{agent_name} explotó")
        return {"answer": f"ok {agent_name}", "steps": []}


async def _correr(runtime, steps):
    engine = WorkflowEngine(workflows_dir="", runtime=runtime, tool_registry=None)
    await engine.bootstrap()
    engine.register_workflow(WorkflowSpec(name="wf", steps=steps))
    return await engine.run("wf", trigger={})


async def test_continue_sigue_con_el_resto():
    runtime = _RuntimeQueRompe({"malo"})
    result = await _correr(
        runtime,
        [
            StepSpec(name="uno", agent="malo", input_template="x", on_error="continue"),
            StepSpec(name="dos", agent="bueno", input_template="x"),
        ],
    )

    assert result.status == "completed"
    assert result.steps["uno"].status == StepStatus.ERROR
    assert result.steps["dos"].status == StepStatus.SUCCESS
    assert "bueno" in runtime.llamados


async def test_sin_on_error_corta_el_run():
    """Comportamiento histórico: el default sigue siendo cortar."""
    runtime = _RuntimeQueRompe({"malo"})
    result = await _correr(
        runtime,
        [
            StepSpec(name="uno", agent="malo", input_template="x"),
            StepSpec(name="dos", agent="bueno", input_template="x"),
        ],
    )

    assert result.status == "failed"
    assert "bueno" not in runtime.llamados


async def test_continue_deja_el_error_en_contexto():
    runtime = _RuntimeQueRompe({"malo"})
    result = await _correr(
        runtime,
        [
            StepSpec(name="uno", agent="malo", input_template="x", on_error="continue"),
            StepSpec(name="dos", agent="bueno", input_template="x"),
        ],
    )

    assert result.steps["uno"].error
    assert "explotó" in result.steps["uno"].error
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
uv run pytest tests/test_workflow_on_error_continue.py -v
```

Esperado: `test_continue_sigue_con_el_resto` FALLA con `assert 'failed' == 'completed'` — hoy `on_error="continue"` no está en `step_index`, así que cae al `status = "failed"; break`.

- [ ] **Step 3: Implementar**

En `astromesh/workflow/__init__.py`, dentro de `_drive`, en el bloque `if result.status == WfStepStatus.ERROR:`, **antes** del `if step.on_error and step.on_error != "fail":` existente:

```python
                    if step.on_error == "continue":
                        # Efecto secundario opcional: se registra el fallo y la
                        # corrida sigue. Sin esto, `continue` caía al else y
                        # tumbaba el workflow como cualquier otro nombre de paso
                        # que no existiera.
                        context["steps"][step.name] = {"output": None, "error": result.error}
                        run.current_index = i + 1
                        run.updated_at = datetime.now(UTC).isoformat()
                        await self._store.save(run)
                        i += 1
                        continue
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

```bash
uv run pytest tests/test_workflow_on_error_continue.py -v
uv run pytest tests/ -k workflow -v
```

Esperado: todo PASS.

- [ ] **Step 5: Lint y commit**

```bash
uv run ruff format astromesh/workflow/ tests/test_workflow_on_error_continue.py
uv run ruff check astromesh/workflow/ tests/test_workflow_on_error_continue.py
git add astromesh/workflow/__init__.py tests/test_workflow_on_error_continue.py CHANGELOG.md
git commit -m "feat(workflow): on_error: continue registra el fallo y sigue la corrida"
```

Entrada de `CHANGELOG.md` bajo `### Added (Backend)`:

```markdown
- **Workflows**: `on_error: continue` en un paso registra el error y sigue con el resto de
  la corrida, para efectos secundarios opcionales. El default sin declarar sigue siendo
  cortar el workflow.
```

---

## Task 8: `StepType.PARALLEL`

**Files:**
- Modify: `astromesh/workflow/models.py` — `StepType`, `StepSpec` (campo `parallel` y `__post_init__`), `step_type`
- Modify: `astromesh/workflow/executor.py` — `_dispatch`, nuevo `_run_parallel`
- Modify: `astromesh/workflow/__init__.py` — `_drive` aplana los sub-resultados y mergea `_when`
- Modify: `astromesh/workflow/loader.py` — `_parse_step` parsea `parallel`
- Test: `tests/test_workflow_parallel.py` (crear)

**Interfaces:**
- Consumes: `execute_step` con guarda `when` de la Task 6.
- Produces:
  - `StepSpec(..., parallel: list[StepSpec] | None = None)`
  - salida de un paso paralelo: `{"results": {<sub>: <output>}, "_when": {<sub>: bool}, "_errors": {<sub>: str}}`
  - `_drive` registra cada sub-resultado en `context["steps"][<sub>]` y en `WorkflowRunResult.steps`.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_workflow_parallel.py`:

```python
"""Paso PARALLEL: los sub-pasos corren a la vez y sus outputs se mergean al contexto."""

import asyncio

from astromesh.workflow import WorkflowEngine
from astromesh.workflow.models import StepSpec, StepStatus, WorkflowSpec


class _RuntimeLento:
    """Duerme `demora` por agente para que el paralelismo sea observable."""

    def __init__(self, demora=0.05, rotos=()):
        self._demora = demora
        self._rotos = set(rotos)
        self.llamados = []

    async def run(self, agent_name, query, session_id, context=None, parent_trace_id=None, **kw):
        await asyncio.sleep(self._demora)
        self.llamados.append(agent_name)
        if agent_name in self._rotos:
            raise RuntimeError(f"{agent_name} explotó")
        return {"answer": f"ok {agent_name}", "steps": []}


async def _correr(runtime, steps, trigger=None):
    engine = WorkflowEngine(workflows_dir="", runtime=runtime, tool_registry=None)
    await engine.bootstrap()
    engine.register_workflow(WorkflowSpec(name="wf", steps=steps))
    return await engine.run("wf", trigger=trigger or {})


def _paralelo(*subs):
    return StepSpec(name="fanout", parallel=list(subs))


async def test_los_subpasos_corren_concurrentemente():
    runtime = _RuntimeLento(demora=0.1)
    inicio = asyncio.get_event_loop().time()

    await _correr(
        runtime,
        [
            _paralelo(
                StepSpec(name="a", agent="uno", input_template="x"),
                StepSpec(name="b", agent="dos", input_template="x"),
                StepSpec(name="c", agent="tres", input_template="x"),
            )
        ],
    )

    transcurrido = asyncio.get_event_loop().time() - inicio
    assert transcurrido < 0.25, f"parecen secuenciales: tardó {transcurrido:.2f}s para 3x0.1s"
    assert set(runtime.llamados) == {"uno", "dos", "tres"}


async def test_cada_subresultado_queda_direccionable_por_nombre():
    runtime = _RuntimeLento(demora=0)
    result = await _correr(
        runtime,
        [
            _paralelo(
                StepSpec(name="a", agent="uno", input_template="x"),
                StepSpec(name="b", agent="dos", input_template="x"),
            )
        ],
    )

    assert result.steps["a"].status == StepStatus.SUCCESS
    assert result.steps["b"].status == StepStatus.SUCCESS
    assert result.steps["a"].output["answer"] == "ok uno"


async def test_una_rama_que_falla_no_tumba_a_las_hermanas():
    runtime = _RuntimeLento(demora=0, rotos={"malo"})
    result = await _correr(
        runtime,
        [
            _paralelo(
                StepSpec(name="a", agent="malo", input_template="x", on_error="continue"),
                StepSpec(name="b", agent="bueno", input_template="x"),
            )
        ],
    )

    assert result.steps["a"].status == StepStatus.ERROR
    assert result.steps["b"].status == StepStatus.SUCCESS


async def test_guardas_de_subpasos_se_respetan():
    runtime = _RuntimeLento(demora=0)
    result = await _correr(
        runtime,
        [
            _paralelo(
                StepSpec(name="a", agent="uno", input_template="x", when="{{ trigger.n > 7 }}"),
                StepSpec(name="b", agent="dos", input_template="x", when="{{ trigger.n < 7 }}"),
            )
        ],
        trigger={"n": 9},
    )

    assert result.steps["a"].status == StepStatus.SUCCESS
    assert result.steps["b"].status == StepStatus.SKIPPED
    assert runtime.llamados == ["uno"]


async def test_las_guardas_quedan_en_el_slot_when():
    """El paso siguiente puede leer `when.<sub>` para decidir."""
    runtime = _RuntimeLento(demora=0)
    result = await _correr(
        runtime,
        [
            _paralelo(
                StepSpec(name="a", agent="uno", input_template="x", when="{{ trigger.n > 7 }}"),
            ),
            StepSpec(name="tardio", agent="tres", input_template="x", when="{{ not when.a }}"),
        ],
        trigger={"n": 2},
    )

    assert result.steps["a"].status == StepStatus.SKIPPED
    assert result.steps["tardio"].status == StepStatus.SUCCESS


async def test_retry_por_rama():
    class _RuntimeIntermitente:
        def __init__(self):
            self.intentos = 0

        async def run(self, agent_name, query, session_id, context=None, **kw):
            self.intentos += 1
            if self.intentos < 3:
                raise RuntimeError("todavía no")
            return {"answer": "ok", "steps": []}

    runtime = _RuntimeIntermitente()
    result = await _correr(
        runtime,
        [
            _paralelo(
                StepSpec(
                    name="a",
                    agent="uno",
                    input_template="x",
                    retry={"max_attempts": 3, "initial_delay_seconds": 0},
                )
            )
        ],
    )

    assert result.steps["a"].status == StepStatus.SUCCESS
    assert runtime.intentos == 3


async def test_step_spec_rechaza_parallel_junto_a_agent():
    import pytest

    with pytest.raises(ValueError, match="exactly one"):
        StepSpec(name="x", agent="a", parallel=[StepSpec(name="s", agent="b")])
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
uv run pytest tests/test_workflow_parallel.py -v
```

Esperado: FALLA con `TypeError: __init__() got an unexpected keyword argument 'parallel'`.

- [ ] **Step 3: Agregar el tipo y el campo al modelo**

En `astromesh/workflow/models.py`:

En `StepType`, agregar:

```python
    PARALLEL = "parallel"
```

En `StepSpec`, agregar el campo:

```python
    parallel: list["StepSpec"] | None = None
```

En `__post_init__`, incluir `parallel` en la cuenta de tipos y coercionar sub-steps dict:

```python
        if self.parallel is not None:
            self.parallel = [
                p if isinstance(p, StepSpec) else StepSpec(**p) for p in self.parallel
            ]
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
```

En `step_type`, agregar antes del `return StepType.SWITCH` final:

```python
        if self.parallel is not None:
            return StepType.PARALLEL
```

- [ ] **Step 4: Implementar `_run_parallel` en el executor**

En `astromesh/workflow/executor.py`, en `_dispatch`, agregar antes del `raise ValueError` final:

```python
        if step.step_type == StepType.PARALLEL:
            return await self._run_parallel(step, context, start)
```

Y el método:

```python
    async def _run_parallel(self, step: StepSpec, ctx: dict, start: float) -> StepResult:
        """Corre los sub-pasos a la vez y mergea sus salidas.

        Cada sub-paso es un StepSpec completo, así que `when`, `retry`,
        `timeout_seconds` y `on_error` funcionan por rama sin código nuevo. Las
        guardas se evalúan todas contra el mismo contexto: ninguna rama puede ver
        el resultado de una hermana, que es la consecuencia de correr en paralelo.
        """
        subs = step.parallel or []
        resultados = await asyncio.gather(
            *(self.execute_step(sub, ctx) for sub in subs), return_exceptions=True
        )

        salidas: dict[str, Any] = {}
        guardas: dict[str, bool] = {}
        errores: dict[str, str] = {}
        sub_results: dict[str, StepResult] = {}

        for sub, res in zip(subs, resultados, strict=True):
            if isinstance(res, BaseException):
                res = StepResult(name=sub.name, status=StepStatus.ERROR, error=str(res))
            sub_results[sub.name] = res
            if res.condition_matched is not None:
                guardas[sub.name] = res.condition_matched
            if res.status == StepStatus.ERROR:
                errores[sub.name] = res.error or "error sin detalle"
            else:
                salidas[sub.name] = res.output

        elapsed = (time.time() - start) * 1000
        # Una rama rota sólo tumba el paso si NO pidió `on_error: continue`;
        # así el paso paralelo hereda la misma política que los secuenciales.
        fatales = [
            n for n, r in sub_results.items()
            if r.status == StepStatus.ERROR
            and (next(s for s in subs if s.name == n).on_error != "continue")
        ]
        status = StepStatus.ERROR if fatales else StepStatus.SUCCESS
        return StepResult(
            name=step.name,
            status=status,
            output={
                "results": salidas,
                "_when": guardas,
                "_errors": errores,
                "_sub_results": sub_results,
            },
            error="; ".join(f"{n}: {errores[n]}" for n in fatales) or None,
            duration_ms=elapsed,
        )
```

Agregar `from typing import Any` al encabezado si no está.

- [ ] **Step 5: Aplanar los sub-resultados en `_drive`**

En `astromesh/workflow/__init__.py`, en `_drive`, justo después de `step_results[step.name] = result` y antes del manejo del slot `when` de la Task 6:

```python
                if step.step_type == StepType.PARALLEL and isinstance(result.output, dict):
                    # Cada rama queda direccionable por su propio nombre, igual que
                    # si hubiera sido un paso suelto: `steps.<rama>` y el resultado
                    # de la corrida los listan uno por uno.
                    for sub_name, sub_result in (result.output.get("_sub_results") or {}).items():
                        step_results[sub_name] = sub_result
                        context["steps"][sub_name] = {"output": sub_result.output}
                    context.setdefault("when", {}).update(result.output.get("_when") or {})
```

Verificar que `StepType` esté importado en el módulo (ya lo está: `from astromesh.workflow.models import StepType, ...`).

- [ ] **Step 6: Parsear `parallel` en el loader**

En `astromesh/workflow/loader.py`, en `_parse_step`:

```python
        parallel_raw = raw.get("parallel")
        parallel = [self._parse_step(sub) for sub in parallel_raw] if parallel_raw else None
```

y agregar `parallel=parallel,` al `StepSpec(...)`.

- [ ] **Step 7: Correr los tests y verificar que pasan**

```bash
uv run pytest tests/test_workflow_parallel.py -v
uv run pytest tests/ -k workflow -v
```

Esperado: todo PASS.

- [ ] **Step 8: Lint y commit**

```bash
uv run ruff format astromesh/workflow/ tests/test_workflow_parallel.py
uv run ruff check astromesh/workflow/ tests/test_workflow_parallel.py
git add astromesh/workflow/ tests/test_workflow_parallel.py CHANGELOG.md
git commit -m "feat(workflow): paso parallel con fan-out por asyncio.gather"
```

Entrada de `CHANGELOG.md` bajo `### Added (Backend)`:

```markdown
- **Workflows**: nuevo tipo de paso `parallel` — corre una lista de sub-pasos a la vez y
  mergea sus salidas al contexto, cada una direccionable por su nombre. Los sub-pasos son
  pasos completos, así que `when`, `retry`, `timeout_seconds` y `on_error` funcionan por rama.
```

---

## Task 9: `ChainSpec` / `ChainLink`

**Files:**
- Create: `astromesh/chain/models.py`
- Test: `tests/test_chain_models.py` (crear)

**Interfaces:**
- Produces:
  - `ChainLink(agent, when=None, input=None, default=False, retry=None, timeout_seconds=None, on_error=None)`
  - `ChainSpec(mode="sequential", max_depth=5, links=[])`
  - `ChainSpec.from_dict(raw: dict) -> ChainSpec`
  - La Task 10 las consume.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_chain_models.py`:

```python
"""Parseo de spec.chain del YAML del agente."""

import pytest

from astromesh.chain.models import ChainSpec


def test_parseo_minimo():
    spec = ChainSpec.from_dict({"on_complete": [{"agent": "b"}]})
    assert spec.mode == "sequential"
    assert spec.max_depth == 5
    assert len(spec.links) == 1
    assert spec.links[0].agent == "b"
    assert spec.links[0].when is None
    assert spec.links[0].default is False


def test_input_por_defecto():
    """Un eslabón sin `input` recibe la answer del agente anterior."""
    spec = ChainSpec.from_dict({"on_complete": [{"agent": "b"}]})
    assert spec.links[0].input == "{{ output.answer }}"


def test_input_explicito_gana():
    spec = ChainSpec.from_dict({"on_complete": [{"agent": "b", "input": "{{ output.data.x }}"}]})
    assert spec.links[0].input == "{{ output.data.x }}"


def test_modo_paralelo():
    spec = ChainSpec.from_dict({"mode": "parallel", "on_complete": [{"agent": "b"}]})
    assert spec.mode == "parallel"


def test_modo_invalido():
    with pytest.raises(ValueError, match="mode"):
        ChainSpec.from_dict({"mode": "turbo", "on_complete": [{"agent": "b"}]})


def test_campos_de_step_spec_pasan():
    spec = ChainSpec.from_dict(
        {
            "on_complete": [
                {
                    "agent": "b",
                    "when": "{{ output.data.score > 7 }}",
                    "retry": {"max_attempts": 3, "backoff": "exponential"},
                    "timeout_seconds": 30,
                    "on_error": "continue",
                }
            ]
        }
    )
    link = spec.links[0]
    assert link.when == "{{ output.data.score > 7 }}"
    assert link.retry == {"max_attempts": 3, "backoff": "exponential"}
    assert link.timeout_seconds == 30
    assert link.on_error == "continue"


def test_regla_default():
    spec = ChainSpec.from_dict({"on_complete": [{"agent": "b", "default": True}]})
    assert spec.links[0].default is True


def test_default_con_when_es_invalido():
    with pytest.raises(ValueError, match="default"):
        ChainSpec.from_dict({"on_complete": [{"agent": "b", "default": True, "when": "{{ x }}"}]})


def test_dos_defaults_es_invalido():
    with pytest.raises(ValueError, match="default"):
        ChainSpec.from_dict(
            {"on_complete": [{"agent": "b", "default": True}, {"agent": "c", "default": True}]}
        )


def test_eslabon_sin_agent_es_invalido():
    with pytest.raises(ValueError, match="agent"):
        ChainSpec.from_dict({"on_complete": [{"when": "{{ x }}"}]})


def test_on_complete_vacio_es_invalido():
    with pytest.raises(ValueError, match="on_complete"):
        ChainSpec.from_dict({"on_complete": []})


def test_max_depth_debe_ser_positivo():
    with pytest.raises(ValueError, match="max_depth"):
        ChainSpec.from_dict({"max_depth": 0, "on_complete": [{"agent": "b"}]})


def test_when_que_referencia_hermano_en_paralelo_es_invalido():
    """En paralelo todas las guardas se evalúan antes de arrancar cualquier rama."""
    with pytest.raises(ValueError, match="steps\\."):
        ChainSpec.from_dict(
            {
                "mode": "parallel",
                "on_complete": [
                    {"agent": "b"},
                    {"agent": "c", "when": "{{ steps.b.output.answer }}"},
                ],
            }
        )


def test_when_que_referencia_hermano_en_secuencial_es_valido():
    spec = ChainSpec.from_dict(
        {"on_complete": [{"agent": "b"}, {"agent": "c", "when": "{{ steps.b.output.answer }}"}]}
    )
    assert len(spec.links) == 2
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
uv run pytest tests/test_chain_models.py -v
```

Esperado: FALLA con `ModuleNotFoundError: No module named 'astromesh.chain.models'`.

- [ ] **Step 3: Implementar**

Crear `astromesh/chain/models.py`:

```python
"""Modelos de `spec.chain`: la declaración de encadenamiento en el YAML del agente."""

from __future__ import annotations

from dataclasses import dataclass, field

_MODOS = ("sequential", "parallel")
_INPUT_POR_DEFECTO = "{{ output.answer }}"


@dataclass
class ChainLink:
    """Un eslabón: un agente a disparar, con su condición y su política de fallo."""

    agent: str
    when: str | None = None
    input: str = _INPUT_POR_DEFECTO
    default: bool = False
    retry: dict | None = None
    timeout_seconds: int | None = None
    on_error: str | None = None


@dataclass
class ChainSpec:
    """La cadena completa de un agente."""

    mode: str = "sequential"
    max_depth: int = 5
    links: list[ChainLink] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict) -> ChainSpec:
        mode = raw.get("mode", "sequential")
        if mode not in _MODOS:
            raise ValueError(f"chain.mode inválido: {mode!r} (esperado uno de {_MODOS})")

        max_depth = raw.get("max_depth", 5)
        if not isinstance(max_depth, int) or max_depth < 1:
            raise ValueError(f"chain.max_depth debe ser un entero >= 1, llegó {max_depth!r}")

        crudos = raw.get("on_complete") or []
        if not crudos:
            raise ValueError("chain.on_complete no puede estar vacío")

        links = [cls._parse_link(c, i) for i, c in enumerate(crudos)]

        defaults = [link for link in links if link.default]
        if len(defaults) > 1:
            nombres = ", ".join(link.agent for link in defaults)
            raise ValueError(f"chain.on_complete tiene más de una regla default: {nombres}")

        if mode == "parallel":
            cls._rechazar_referencias_entre_hermanos(links)

        return cls(mode=mode, max_depth=max_depth, links=links)

    @staticmethod
    def _parse_link(raw: dict, idx: int) -> ChainLink:
        agent = raw.get("agent")
        if not agent:
            raise ValueError(f"chain.on_complete[{idx}] no declara `agent`")

        es_default = bool(raw.get("default", False))
        when = raw.get("when")
        if es_default and when is not None:
            raise ValueError(
                f"chain.on_complete[{idx}] ({agent}) declara `default` y `when` a la vez: "
                "un default dispara cuando ningún `when` matcheó, no puede tener el suyo"
            )

        return ChainLink(
            agent=agent,
            when=when,
            input=raw.get("input") or _INPUT_POR_DEFECTO,
            default=es_default,
            retry=raw.get("retry"),
            timeout_seconds=raw.get("timeout_seconds"),
            on_error=raw.get("on_error"),
        )

    @staticmethod
    def _rechazar_referencias_entre_hermanos(links: list[ChainLink]) -> None:
        """En `parallel` las guardas se evalúan todas antes de arrancar cualquier
        rama, así que un `when` que mira a un hermano queda siempre falso. Se
        rechaza en bootstrap en vez de dejarlo fallar callado en producción."""
        hermanos = {link.agent for link in links}
        for link in links:
            if not link.when:
                continue
            for hermano in hermanos:
                if f"steps.{hermano}" in link.when:
                    raise ValueError(
                        f"el `when` del eslabón '{link.agent}' referencia a 'steps.{hermano}', "
                        "un hermano de la misma cadena `parallel`. En paralelo todas las "
                        "guardas se evalúan antes de que corra ninguna rama, así que esa "
                        "condición sería siempre falsa. Usá mode: sequential."
                    )
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

```bash
uv run pytest tests/test_chain_models.py -v
```

Esperado: 14 PASS.

- [ ] **Step 5: Lint y commit**

```bash
uv run ruff format astromesh/chain/ tests/test_chain_models.py
uv run ruff check astromesh/chain/ tests/test_chain_models.py
git add astromesh/chain/models.py tests/test_chain_models.py
git commit -m "test: modelos de spec.chain con validación de declaración"
```

---

## Task 10: El compilador de cadenas

**Files:**
- Create: `astromesh/chain/compiler.py`
- Modify: `astromesh/chain/__init__.py` (exports)
- Test: `tests/test_chain_compiler.py` (crear)

**Interfaces:**
- Consumes: `ChainSpec`, `ChainLink` (Task 9); `StepSpec`, `WorkflowSpec`, `RetryConfig` de `astromesh/workflow/models.py`.
- Produces:
  - `CHAIN_PREFIX = "__chain__"`
  - `chain_workflow_name(agent_name: str) -> str`
  - `compile_chain(agent_name: str, agent_configs: dict[str, dict]) -> WorkflowSpec`
  - `chain_graph(agent_name: str, agent_configs: dict[str, dict]) -> dict` — el grafo expandido, para `GET /v1/agents/{n}/chain`
  - Las Tasks 11 y 12 las usan.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_chain_compiler.py`:

```python
"""compile_chain: spec.chain -> WorkflowSpec ejecutable por el motor."""

import pytest

from astromesh.chain.compiler import chain_graph, chain_workflow_name, compile_chain
from astromesh.workflow.models import StepType


def _agente(nombre, chain=None, output_schema=None):
    spec = {"identity": {"description": nombre}}
    if chain:
        spec["chain"] = chain
    if output_schema:
        spec["output_schema"] = output_schema
    return {"apiVersion": "astromesh/v1", "kind": "Agent", "metadata": {"name": nombre},
            "spec": spec}


def _configs(*agentes):
    return {a["metadata"]["name"]: a for a in agentes}


def test_nombre_reservado():
    assert chain_workflow_name("a") == "__chain__a"


def test_el_paso_cero_es_el_agente_mismo():
    configs = _configs(_agente("a", {"on_complete": [{"agent": "b"}]}), _agente("b"))
    wf = compile_chain("a", configs)

    assert wf.name == "__chain__a"
    assert wf.steps[0].agent == "a"
    assert wf.steps[0].step_type == StepType.AGENT
    assert wf.steps[0].input_template == "{{ trigger.query }}"
    assert wf.steps[0].when is None, "el agente invocado siempre corre"


def test_un_paso_por_eslabon_con_su_guarda():
    configs = _configs(
        _agente(
            "a",
            {"on_complete": [{"agent": "b", "when": "{{ output.data.score > 7 }}"}, {"agent": "c"}]},
        ),
        _agente("b"),
        _agente("c"),
    )
    wf = compile_chain("a", configs)

    assert [s.agent for s in wf.steps] == ["a", "b", "c"]
    assert wf.steps[1].when == "{{ output.data.score > 7 }}"
    assert wf.steps[2].when is None, "un eslabón sin `when` dispara siempre"


def test_las_guardas_son_estrictas():
    configs = _configs(_agente("a", {"on_complete": [{"agent": "b", "when": "{{ x }}"}]}),
                       _agente("b"))
    wf = compile_chain("a", configs)
    assert wf.steps[1].strict_conditions is True


def test_output_apunta_al_agente_anterior():
    """`output` en un eslabón de A se reescribe a `steps.<A>.output`."""
    configs = _configs(
        _agente("a", {"on_complete": [{"agent": "b", "when": "{{ output.data.score > 7 }}"}]}),
        _agente("b"),
    )
    wf = compile_chain("a", configs)

    assert wf.steps[1].when == "{{ steps.a.output.data.score > 7 }}"
    assert wf.steps[1].input_template == "{{ steps.a.output.answer }}"


def test_regla_default_niega_las_guardas_previas():
    configs = _configs(
        _agente(
            "a",
            {
                "on_complete": [
                    {"agent": "b", "when": "{{ output.data.score > 7 }}"},
                    {"agent": "c"},
                    {"agent": "d", "default": True},
                ]
            },
        ),
        _agente("b"),
        _agente("c"),
        _agente("d"),
    )
    wf = compile_chain("a", configs)

    paso_default = wf.steps[3]
    assert paso_default.agent == "d"
    # sólo `b` tiene guarda; `c` no cuenta como match
    assert paso_default.when == "{{ not (when['a__b']) }}"


def test_default_sin_guardas_previas_dispara_siempre():
    configs = _configs(
        _agente("a", {"on_complete": [{"agent": "b"}, {"agent": "c", "default": True}]}),
        _agente("b"),
        _agente("c"),
    )
    wf = compile_chain("a", configs)
    assert wf.steps[2].when is None


def test_modo_paralelo_produce_un_paso_parallel():
    configs = _configs(
        _agente("a", {"mode": "parallel", "on_complete": [{"agent": "b"}, {"agent": "c"}]}),
        _agente("b"),
        _agente("c"),
    )
    wf = compile_chain("a", configs)

    assert wf.steps[1].step_type == StepType.PARALLEL
    assert [s.agent for s in wf.steps[1].parallel] == ["b", "c"]


def test_paralelo_deja_el_default_como_paso_posterior():
    """El default necesita las guardas ya evaluadas, así que va después del fanout."""
    configs = _configs(
        _agente(
            "a",
            {
                "mode": "parallel",
                "on_complete": [
                    {"agent": "b", "when": "{{ output.data.score > 7 }}"},
                    {"agent": "c", "default": True},
                ],
            },
        ),
        _agente("b"),
        _agente("c"),
    )
    wf = compile_chain("a", configs)

    assert wf.steps[1].step_type == StepType.PARALLEL
    assert wf.steps[2].agent == "c"
    assert wf.steps[2].when == "{{ not (when['a__b']) }}"


def test_campos_de_fallo_se_propagan():
    configs = _configs(
        _agente(
            "a",
            {
                "on_complete": [
                    {
                        "agent": "b",
                        "retry": {"max_attempts": 3, "backoff": "exponential"},
                        "timeout_seconds": 30,
                        "on_error": "continue",
                    }
                ]
            },
        ),
        _agente("b"),
    )
    wf = compile_chain("a", configs)

    assert wf.steps[1].retry.max_attempts == 3
    assert wf.steps[1].retry.backoff == "exponential"
    assert wf.steps[1].timeout_seconds == 30
    assert wf.steps[1].on_error == "continue"


def test_expansion_recursiva():
    configs = _configs(
        _agente("a", {"on_complete": [{"agent": "b"}]}),
        _agente("b", {"on_complete": [{"agent": "c"}]}),
        _agente("c"),
    )
    wf = compile_chain("a", configs)

    assert [s.agent for s in wf.steps] == ["a", "b", "c"]


def test_la_guarda_anidada_apunta_a_su_propio_padre():
    configs = _configs(
        _agente("a", {"on_complete": [{"agent": "b"}]}),
        _agente("b", {"on_complete": [{"agent": "c", "when": "{{ output.data.ok }}"}]}),
        _agente("c"),
    )
    wf = compile_chain("a", configs)

    assert wf.steps[2].when == "{{ steps.b.output.data.ok }}"


def test_ciclo_da_error_nombrando_la_ruta():
    configs = _configs(
        _agente("a", {"on_complete": [{"agent": "b"}]}),
        _agente("b", {"on_complete": [{"agent": "a"}]}),
    )
    with pytest.raises(ValueError, match="ciclo"):
        compile_chain("a", configs)

    with pytest.raises(ValueError, match="a -> b -> a"):
        compile_chain("a", configs)


def test_max_depth_excedido_da_error():
    configs = _configs(
        _agente("a", {"max_depth": 2, "on_complete": [{"agent": "b"}]}),
        _agente("b", {"on_complete": [{"agent": "c"}]}),
        _agente("c", {"on_complete": [{"agent": "d"}]}),
        _agente("d"),
    )
    with pytest.raises(ValueError, match="max_depth"):
        compile_chain("a", configs)


def test_agente_inexistente_da_error_nombrando_al_referente():
    configs = _configs(_agente("a", {"on_complete": [{"agent": "fantasma"}]}))
    with pytest.raises(ValueError, match="fantasma"):
        compile_chain("a", configs)
    with pytest.raises(ValueError, match="'a'"):
        compile_chain("a", configs)


def test_agente_sin_cadena_no_compila():
    configs = _configs(_agente("a"))
    assert compile_chain("a", configs) is None


def test_grafo_expandido():
    configs = _configs(
        _agente("a", {"on_complete": [{"agent": "b", "when": "{{ output.data.score > 7 }}"}]}),
        _agente("b", {"on_complete": [{"agent": "c"}]}),
        _agente("c"),
    )
    grafo = chain_graph("a", configs)

    assert grafo["agent"] == "a"
    assert grafo["mode"] == "sequential"
    assert grafo["max_depth"] == 5
    assert grafo["links"][0] == {
        "agent": "b",
        "depth": 1,
        "via": None,
        "when": "{{ output.data.score > 7 }}",
        "default": False,
    }
    assert grafo["links"][1] == {
        "agent": "c",
        "depth": 2,
        "via": "b",
        "when": None,
        "default": False,
    }
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
uv run pytest tests/test_chain_compiler.py -v
```

Esperado: FALLA con `ModuleNotFoundError: No module named 'astromesh.chain.compiler'`.

- [ ] **Step 3: Implementar**

Crear `astromesh/chain/compiler.py`:

```python
"""Compila `spec.chain` a un WorkflowSpec que el motor ya sabe ejecutar.

Se compila en bootstrap, no en runtime. Eso hace que un ciclo, un max_depth
excedido o un agente inexistente exploten al arrancar —con la ruta completa en
el mensaje— en vez de a mitad de una corrida en producción, y deja la cadena
expandida disponible para inspección sin ejecutar nada.
"""

from __future__ import annotations

import re

from astromesh.chain.models import ChainSpec
from astromesh.workflow.models import RetryConfig, StepSpec, WorkflowSpec

CHAIN_PREFIX = "__chain__"

# `output.` en una cadena refiere al agente inmediatamente anterior. En el
# contexto del workflow eso vive en `steps.<agente>.output`, así que se reescribe
# al compilar. Con borde de palabra para no tocar `my_output.x`.
_OUTPUT_REF = re.compile(r"\boutput\.")


def chain_workflow_name(agent_name: str) -> str:
    return f"{CHAIN_PREFIX}{agent_name}"


def _chain_of(agent_name: str, agent_configs: dict) -> ChainSpec | None:
    config = agent_configs.get(agent_name)
    if not config:
        return None
    raw = (config.get("spec") or {}).get("chain")
    return ChainSpec.from_dict(raw) if raw else None


def _rebind(expr: str | None, padre: str) -> str | None:
    """Reescribe `output.x` a `steps.<padre>.output.x`."""
    if not expr:
        return expr
    return _OUTPUT_REF.sub(f"steps.{padre}.output.", expr)


def _step_name(padre: str, hijo: str) -> str:
    """Nombre único de paso: un mismo agente puede aparecer bajo dos padres."""
    return f"{padre}__{hijo}"


def compile_chain(agent_name: str, agent_configs: dict) -> WorkflowSpec | None:
    """Devuelve el WorkflowSpec de la cadena de `agent_name`, o None si no declara."""
    raiz = _chain_of(agent_name, agent_configs)
    if raiz is None:
        return None

    steps: list[StepSpec] = [
        StepSpec(name=agent_name, agent=agent_name, input_template="{{ trigger.query }}")
    ]
    _expandir(agent_name, raiz, agent_configs, steps, ruta=[agent_name], max_depth=raiz.max_depth)

    return WorkflowSpec(
        name=chain_workflow_name(agent_name),
        description=f"cadena compilada del agente '{agent_name}'",
        steps=steps,
    )


def _expandir(
    padre: str,
    chain: ChainSpec,
    agent_configs: dict,
    steps: list[StepSpec],
    ruta: list[str],
    max_depth: int,
) -> None:
    profundidad = len(ruta)
    if profundidad > max_depth:
        raise ValueError(
            f"cadena del agente '{ruta[0]}': se excedió max_depth={max_depth} "
            f"en la ruta {' -> '.join(ruta)}"
        )

    guardados: list[str] = []  # nombres de paso con `when`, para armar el default
    normales = [link for link in chain.links if not link.default]
    default = next((link for link in chain.links if link.default), None)

    for link in normales:
        if link.agent not in agent_configs:
            raise ValueError(
                f"el agente '{link.agent}', referenciado por la cadena de '{padre}', no existe"
            )
        if link.agent in ruta:
            raise ValueError(
                f"cadena del agente '{ruta[0]}': ciclo detectado en la ruta "
                f"{' -> '.join([*ruta, link.agent])}"
            )
        nombre = _step_name(padre, link.agent)
        if link.when:
            guardados.append(nombre)

    sub_steps = [
        _a_step(link, padre, _step_name(padre, link.agent)) for link in normales
    ]

    if chain.mode == "parallel" and sub_steps:
        steps.append(StepSpec(name=f"{padre}__fanout", parallel=sub_steps))
    else:
        steps.extend(sub_steps)

    if default is not None:
        if default.agent not in agent_configs:
            raise ValueError(
                f"el agente '{default.agent}', referenciado por la cadena de '{padre}', no existe"
            )
        if default.agent in ruta:
            raise ValueError(
                f"cadena del agente '{ruta[0]}': ciclo detectado en la ruta "
                f"{' -> '.join([*ruta, default.agent])}"
            )
        # El default dispara sólo si ninguna guarda hermana matcheó. Se lee del
        # slot `when` que el motor publica por paso. Va siempre como paso suelto,
        # también en `parallel`: necesita las guardas ya evaluadas.
        paso = _a_step(default, padre, _step_name(padre, default.agent))
        if guardados:
            negacion = " or ".join(f"when['{n}']" for n in guardados)
            paso.when = f"{{{{ not ({negacion}) }}}}"
            paso.strict_conditions = True
        steps.append(paso)

    for link in [*normales, *([default] if default else [])]:
        anidada = _chain_of(link.agent, agent_configs)
        if anidada is not None:
            _expandir(
                link.agent,
                anidada,
                agent_configs,
                steps,
                ruta=[*ruta, link.agent],
                max_depth=max_depth,
            )


def _a_step(link, padre: str, nombre: str) -> StepSpec:
    return StepSpec(
        name=nombre,
        agent=link.agent,
        input_template=_rebind(link.input, padre),
        when=_rebind(link.when, padre),
        strict_conditions=link.when is not None,
        retry=RetryConfig(**link.retry) if link.retry else None,
        timeout_seconds=link.timeout_seconds,
        on_error=link.on_error,
    )


def chain_graph(agent_name: str, agent_configs: dict) -> dict | None:
    """El grafo expandido, sin ejecutar nada. Alimenta GET /v1/agents/{n}/chain."""
    raiz = _chain_of(agent_name, agent_configs)
    if raiz is None:
        return None

    links: list[dict] = []

    def recorrer(padre: str, chain: ChainSpec, ruta: list[str]) -> None:
        for link in chain.links:
            if link.agent in ruta or len(ruta) >= raiz.max_depth:
                continue
            links.append(
                {
                    "agent": link.agent,
                    "depth": len(ruta),
                    "via": None if len(ruta) == 1 else padre,
                    "when": link.when,
                    "default": link.default,
                }
            )
            anidada = _chain_of(link.agent, agent_configs)
            if anidada is not None:
                recorrer(link.agent, anidada, [*ruta, link.agent])

    recorrer(agent_name, raiz, [agent_name])
    return {
        "agent": agent_name,
        "mode": raiz.mode,
        "max_depth": raiz.max_depth,
        "links": links,
    }
```

Actualizar `astromesh/chain/__init__.py`:

```python
"""Encadenamiento declarativo de agentes (`spec.chain`)."""

from astromesh.chain.compiler import (
    CHAIN_PREFIX,
    chain_graph,
    chain_workflow_name,
    compile_chain,
)
from astromesh.chain.models import ChainLink, ChainSpec

__all__ = [
    "CHAIN_PREFIX",
    "ChainLink",
    "ChainSpec",
    "chain_graph",
    "chain_workflow_name",
    "compile_chain",
]
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

```bash
uv run pytest tests/test_chain_compiler.py -v
```

Esperado: 18 PASS. Si `test_regla_default_niega_las_guardas_previas` falla por el formato exacto del `when` generado, ajustar el **test** al formato real que produce el compilador (el criterio es que la expresión niegue la disyunción de las guardas hermanas), no al revés.

- [ ] **Step 5: Lint y commit**

```bash
uv run ruff format astromesh/chain/ tests/test_chain_compiler.py
uv run ruff check astromesh/chain/ tests/test_chain_compiler.py
git add astromesh/chain/ tests/test_chain_compiler.py
git commit -m "test: compilador de spec.chain a WorkflowSpec con expansión recursiva"
```

---

## Task 11: Registrar las cadenas en el bootstrap y reservar el prefijo

**Files:**
- Modify: `astromesh/runtime/engine.py` — método `bootstrap` de `AgentRuntime`; `deploy_agent`
- Modify: `astromesh/workflow/loader.py` — `_parse` rechaza el prefijo reservado
- Modify: `astromesh/api/main.py` — registrar cadenas después de `workflow_engine.bootstrap()`
- Test: `tests/test_chain_bootstrap.py` (crear)

**Interfaces:**
- Consumes: `compile_chain`, `chain_workflow_name`, `CHAIN_PREFIX` (Task 10); `WorkflowEngine.register_workflow(spec)`; `app.state.workflow_engine` (Task 1).
- Produces: `AgentRuntime.compiled_chains() -> dict[str, WorkflowSpec]` y `AgentRuntime.agent_configs` accesible para la Task 12.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_chain_bootstrap.py`:

```python
"""Las cadenas se compilan y registran al arrancar; los errores explotan ahí."""

import pytest

from astromesh.chain.compiler import chain_workflow_name
from astromesh.runtime.engine import AgentRuntime

BASE = """
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: {nombre}
spec:
  identity:
    description: "agente {nombre}"
  model:
    primary:
      provider: ollama
      model: "test"
      endpoint: "http://localhost:11434"
  prompts:
    system: "hola"
  orchestration:
    pattern: react
{extra}"""


def _escribir(tmp_path, nombre, extra=""):
    agents = tmp_path / "agents"
    agents.mkdir(exist_ok=True)
    (agents / f"{nombre}.agent.yaml").write_text(
        BASE.format(nombre=nombre, extra=extra), encoding="utf-8"
    )


async def test_la_cadena_queda_compilada(tmp_path):
    _escribir(tmp_path, "a", "  chain:\n    on_complete:\n      - agent: b\n")
    _escribir(tmp_path, "b")

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    cadenas = runtime.compiled_chains()
    assert chain_workflow_name("a") in cadenas
    assert [s.agent for s in cadenas[chain_workflow_name("a")].steps] == ["a", "b"]


async def test_agente_sin_cadena_no_produce_workflow(tmp_path):
    _escribir(tmp_path, "solo")

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    assert runtime.compiled_chains() == {}


async def test_ciclo_explota_al_arrancar(tmp_path):
    _escribir(tmp_path, "a", "  chain:\n    on_complete:\n      - agent: b\n")
    _escribir(tmp_path, "b", "  chain:\n    on_complete:\n      - agent: a\n")

    runtime = AgentRuntime(config_dir=str(tmp_path))
    with pytest.raises(ValueError, match="ciclo"):
        await runtime.bootstrap()


async def test_agente_inexistente_explota_al_arrancar(tmp_path):
    _escribir(tmp_path, "a", "  chain:\n    on_complete:\n      - agent: fantasma\n")

    runtime = AgentRuntime(config_dir=str(tmp_path))
    with pytest.raises(ValueError, match="fantasma"):
        await runtime.bootstrap()


def test_el_loader_rechaza_el_prefijo_reservado(tmp_path):
    from astromesh.workflow.loader import WorkflowLoader

    wf = tmp_path / "malo.workflow.yaml"
    wf.write_text(
        """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: __chain__a
spec:
  steps:
    - name: uno
      tool: noop
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="__chain__"):
        WorkflowLoader(str(tmp_path)).load_file(wf)
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
uv run pytest tests/test_chain_bootstrap.py -v
```

Esperado: FALLA con `AttributeError: 'AgentRuntime' object has no attribute 'compiled_chains'`.

- [ ] **Step 3: Compilar las cadenas en el bootstrap del runtime**

En `astromesh/runtime/engine.py`, agregar al import del encabezado:

```python
from astromesh.chain.compiler import chain_workflow_name, compile_chain
```

En `AgentRuntime.__init__`, junto a las otras estructuras (`self._agent_configs`, etc.):

```python
        self._compiled_chains: dict[str, object] = {}
```

Al final de `AgentRuntime.bootstrap()`, después de que `self._agent_configs` esté poblado:

```python
        self._compile_chains()
```

Y agregar los métodos:

```python
    def _compile_chains(self) -> None:
        """Compila la cadena de cada agente que declare `spec.chain`.

        Deliberadamente NO se atrapa la excepción: un ciclo, un max_depth excedido
        o un agente inexistente tienen que impedir el arranque, con la ruta en el
        mensaje. Descubrirlo a mitad de una corrida en producción sería peor.
        """
        self._compiled_chains = {}
        for name in self._agent_configs:
            wf = compile_chain(name, self._agent_configs)
            if wf is not None:
                self._compiled_chains[chain_workflow_name(name)] = wf

    def compiled_chains(self) -> dict:
        """{nombre de workflow: WorkflowSpec} de las cadenas compiladas."""
        return dict(self._compiled_chains)

    @property
    def agent_configs(self) -> dict:
        """Configs crudos de los agentes; los usa la ruta para leer `spec.chain`."""
        return self._agent_configs

    def has_chain(self, agent_name: str) -> bool:
        return chain_workflow_name(agent_name) in self._compiled_chains
```

En `deploy_agent`, después de `self._agent_status[name] = "deployed"`, recompilar para que una cadena registrada en caliente quede disponible:

```python
        self._compile_chains()
```

- [ ] **Step 4: Reservar el prefijo en el loader**

En `astromesh/workflow/loader.py`, en `_parse`, antes de construir el `WorkflowSpec`:

```python
        nombre = metadata["name"]
        if nombre.startswith(CHAIN_PREFIX):
            raise ValueError(
                f"el prefijo '{CHAIN_PREFIX}' está reservado para las cadenas compiladas "
                f"de los agentes; renombrá el workflow '{nombre}'"
            )
```

y usar `name=nombre` en el `WorkflowSpec(...)`. Agregar el import:

```python
from astromesh.chain.compiler import CHAIN_PREFIX
```

- [ ] **Step 5: Registrar las cadenas en el lifespan**

En `astromesh/api/main.py`, dentro del bloque `try` del `WorkflowEngine` (Task 1), después de `await workflow_engine.bootstrap()`:

```python
        for wf_spec in runtime.compiled_chains().values():
            workflow_engine.register_workflow(wf_spec)
```

- [ ] **Step 6: Correr los tests y verificar que pasan**

```bash
uv run pytest tests/test_chain_bootstrap.py tests/test_workflow_wiring.py -v
uv run pytest tests/ -k "chain or workflow or runtime" -v
```

Esperado: todo PASS.

- [ ] **Step 7: Lint y commit**

```bash
uv run ruff format astromesh/ tests/test_chain_bootstrap.py
uv run ruff check astromesh/ tests/test_chain_bootstrap.py
git add astromesh/ tests/test_chain_bootstrap.py CHANGELOG.md
git commit -m "feat(runtime): compilar y registrar las cadenas de agentes en el bootstrap"
```

Entrada de `CHANGELOG.md` bajo `### Added (Backend)`:

```markdown
- **Agentes**: las cadenas declaradas en `spec.chain` se compilan a workflows al arrancar el
  runtime. Un ciclo, un `max_depth` excedido o un agente inexistente impiden el arranque con
  la ruta completa en el mensaje, en vez de fallar a mitad de una corrida. El prefijo
  `__chain__` queda reservado y el loader de workflows lo rechaza.
```

---

## Task 12: La ruta `/run` con cadena y `GET /agents/{n}/chain`

**Files:**
- Modify: `astromesh/api/routes/agents.py:75-79` (`AgentRunResponse`), `:191-236` (`run_agent`), y agregar la ruta nueva
- Test: `tests/test_chain_api.py` (crear)

**Interfaces:**
- Consumes: `runtime.has_chain(name)`, `runtime.compiled_chains()`, `runtime.agent_configs` (Task 11); `chain_graph`, `chain_workflow_name` (Task 10); `app.state.workflow_engine` (Task 1); `WorkflowEngine.run(name, trigger)`.
- Produces: `AgentRunResponse.chain: dict | None` y `GET /v1/agents/{agent_name}/chain`.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_chain_api.py`:

```python
"""La ruta /run devuelve la answer de A más el bloque `chain`."""

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

BASE = """
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: {nombre}
spec:
  identity:
    description: "agente {nombre}"
  model:
    primary:
      provider: ollama
      model: "test"
      endpoint: "http://localhost:11434"
  prompts:
    system: "hola"
  orchestration:
    pattern: react
{extra}"""


@pytest.fixture
def config_dir(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "a.agent.yaml").write_text(
        BASE.format(
            nombre="a",
            extra=(
                "  output_schema:\n"
                "    score: {type: integer}\n"
                "  chain:\n"
                "    on_complete:\n"
                "      - agent: b\n"
                "        when: \"{{ output.data.score > 7 }}\"\n"
                "      - agent: c\n"
            ),
        ),
        encoding="utf-8",
    )
    (agents / "b.agent.yaml").write_text(BASE.format(nombre="b", extra=""), encoding="utf-8")
    (agents / "c.agent.yaml").write_text(BASE.format(nombre="c", extra=""), encoding="utf-8")
    (agents / "solo.agent.yaml").write_text(BASE.format(nombre="solo", extra=""), encoding="utf-8")
    return tmp_path


@pytest.fixture
async def client(config_dir, monkeypatch):
    monkeypatch.setenv("ASTROMESH_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("ASTROMESH_SKIP_RUNTIME", raising=False)
    from astromesh.api.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            c.app_state = app.state
            yield c


def _hacer_execute(respuesta):
    async def execute(query, context, model_fn, tool_fn, tools, max_iterations=10):
        return {"answer": respuesta, "steps": []}

    return execute


def _falsificar_agentes(runtime, respuestas):
    """Hace que cada agente devuelva la respuesta indicada, sin tocar providers."""
    for nombre, agente in runtime._agents.items():
        if nombre in respuestas:
            agente._pattern.execute = _hacer_execute(respuestas[nombre])


async def test_cadena_dispara_y_devuelve_links(client):
    runtime = client.app_state.workflow_engine._runtime
    _falsificar_agentes(
        runtime,
        {
            "a": 'Calificado.\n```json\n{"score": 9}\n```',
            "b": "mail enviado",
            "c": "registrado en crm",
        },
    )

    resp = await client.post("/v1/agents/a/run", json={"query": "un lead", "session_id": "s1"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"].startswith("Calificado."), "la answer debe ser la de A"
    assert body["chain"]["status"] == "completed"

    por_agente = {link["agent"]: link for link in body["chain"]["links"]}
    assert por_agente["b"]["status"] == "success"
    assert por_agente["b"]["answer"] == "mail enviado"
    assert por_agente["c"]["status"] == "success"


async def test_condicion_falsa_deja_el_eslabon_skipped(client):
    runtime = client.app_state.workflow_engine._runtime
    _falsificar_agentes(
        runtime,
        {
            "a": 'Flojo.\n```json\n{"score": 2}\n```',
            "b": "mail enviado",
            "c": "registrado en crm",
        },
    )

    resp = await client.post("/v1/agents/a/run", json={"query": "un lead", "session_id": "s1"})

    body = resp.json()
    por_agente = {link["agent"]: link for link in body["chain"]["links"]}
    assert por_agente["b"]["status"] == "skipped"
    assert por_agente["b"]["reason"] == "condition_false"
    assert por_agente["c"]["status"] == "success", "un eslabón sin `when` dispara igual"


async def test_agente_sin_cadena_no_gana_el_bloque(client):
    """Guarda de regresión: la forma de hoy no cambia para quien no opta."""
    runtime = client.app_state.workflow_engine._runtime
    _falsificar_agentes(runtime, {"solo": "respuesta simple"})

    resp = await client.post("/v1/agents/solo/run", json={"query": "hola", "session_id": "s1"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "respuesta simple"
    assert body["chain"] is None


async def test_grafo_de_la_cadena(client):
    resp = await client.get("/v1/agents/a/chain")

    assert resp.status_code == 200
    grafo = resp.json()
    assert grafo["agent"] == "a"
    assert grafo["mode"] == "sequential"
    assert [link["agent"] for link in grafo["links"]] == ["b", "c"]


async def test_grafo_404_si_no_hay_cadena(client):
    resp = await client.get("/v1/agents/solo/chain")
    assert resp.status_code == 404


async def test_grafo_404_si_no_existe_el_agente(client):
    resp = await client.get("/v1/agents/fantasma/chain")
    assert resp.status_code == 404
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
uv run pytest tests/test_chain_api.py -v
```

Esperado: FALLA — `body["chain"]` da `KeyError`, y `/v1/agents/a/chain` devuelve 404 porque la ruta no existe.

- [ ] **Step 3: Agregar `chain` al modelo de respuesta**

En `astromesh/api/routes/agents.py`, en `AgentRunResponse`:

```python
class AgentRunResponse(BaseModel):
    answer: str
    steps: list[dict] = []
    usage: UsageInfo | None = None
    trace: dict | None = None
    data: dict | None = None
    chain: dict | None = None
```

- [ ] **Step 4: Construir el bloque `chain`**

Agregar en el mismo archivo, arriba de `run_agent`:

```python
def _link_desde_step(agent_name: str, step_result) -> dict:
    """Traduce un StepResult de la cadena al link que ve el cliente."""
    from astromesh.workflow.models import StepStatus

    link = {"agent": agent_name, "status": "success"}
    if step_result.status == StepStatus.SKIPPED:
        link["status"] = "skipped"
        link["reason"] = "condition_false"
        return link
    if step_result.status == StepStatus.ERROR:
        link["status"] = "error"
        link["error"] = step_result.error
        return link

    salida = step_result.output if isinstance(step_result.output, dict) else {}
    link["answer"] = salida.get("answer", "")
    if salida.get("data") is not None:
        link["data"] = salida["data"]
    if step_result.duration_ms is not None:
        link["duration_ms"] = step_result.duration_ms
    return link


def _construir_chain(wf_result, agent_name: str, grafo: dict) -> dict:
    """Arma el bloque `chain` a partir del resultado del workflow compilado."""
    links = []
    hubo_error = False
    for entrada in grafo["links"]:
        # El compilador nombra cada paso `<padre>__<hijo>`.
        padre = entrada["via"] or agent_name
        step = wf_result.steps.get(f"{padre}__{entrada['agent']}")
        if step is None:
            links.append(
                {
                    "agent": entrada["agent"],
                    "depth": entrada["depth"],
                    "via": entrada["via"],
                    "status": "skipped",
                    "reason": "upstream_stopped",
                }
            )
            continue
        link = _link_desde_step(entrada["agent"], step)
        link["depth"] = entrada["depth"]
        link["via"] = entrada["via"]
        hubo_error = hubo_error or link["status"] == "error"
        links.append(link)

    if wf_result.status == "failed":
        status = "failed"
    elif hubo_error:
        status = "partial"
    else:
        status = "completed"

    return {
        "run_id": wf_result.run_id,
        "status": status,
        "mode": grafo["mode"],
        "links": links,
    }
```

- [ ] **Step 5: Ramificar en `run_agent`**

En `run_agent`, reemplazar el bloque que va desde `result = await _runtime.run(...)` hasta el `return AgentRunResponse(...)` por:

```python
        engine = getattr(http_request.app.state, "workflow_engine", None)
        tiene_cadena = getattr(_runtime, "has_chain", lambda _: False)(agent_name)

        if tiene_cadena and engine is not None:
            from astromesh.chain.compiler import chain_graph, chain_workflow_name

            wf_result = await engine.run(
                chain_workflow_name(agent_name),
                trigger={
                    "query": request.query,
                    "session_id": request.session_id,
                    "context": context,
                },
            )
            paso_a = wf_result.steps.get(agent_name)
            result = paso_a.output if paso_a and isinstance(paso_a.output, dict) else {}
            grafo = chain_graph(agent_name, _runtime.agent_configs)
            chain_block = _construir_chain(wf_result, agent_name, grafo)
        else:
            result = await _runtime.run(
                agent_name,
                request.query,
                request.session_id,
                context,
                connections=request.connections,
            )
            chain_block = None

        logger.debug(
            "run_agent done agent=%s session=%s answer_chars=%d steps=%d cadena=%s",
            agent_name,
            request.session_id,
            len(result.get("answer", "") or ""),
            len(result.get("steps") or []),
            bool(chain_block),
        )
        trace = result.get("trace", {})
        usage_data = usage_from_trace(trace)
        usage = UsageInfo(**usage_data) if usage_data else None
        return AgentRunResponse(
            answer=result.get("answer", ""),
            steps=_steps_to_dicts(result.get("steps")),
            usage=usage,
            trace=trace or None,
            data=result.get("data"),
            chain=chain_block,
        )
```

- [ ] **Step 6: Agregar la ruta del grafo**

Al final de `astromesh/api/routes/agents.py`:

```python
@router.get("/agents/{agent_name}/chain")
async def get_agent_chain(agent_name: str):
    """El grafo de la cadena, ya expandido. Es un artefacto de compilación:
    se puede pedir sin ejecutar nada."""
    if not _runtime:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    if agent_name not in _runtime.agent_configs:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    from astromesh.chain.compiler import chain_graph

    grafo = chain_graph(agent_name, _runtime.agent_configs)
    if grafo is None:
        raise HTTPException(
            status_code=404, detail=f"Agent '{agent_name}' does not declare spec.chain"
        )
    return grafo
```

- [ ] **Step 7: Correr los tests y verificar que pasan**

```bash
uv run pytest tests/test_chain_api.py -v
uv run pytest tests/ -v
```

Esperado: **toda** la suite PASS. Prestar atención especial a los tests existentes de `/v1/agents/{n}/run` — `chain` y `data` deben venir en `null` para agentes sin cadena.

- [ ] **Step 8: Lint y commit**

```bash
uv run ruff format astromesh/ tests/test_chain_api.py
uv run ruff check astromesh/ tests/test_chain_api.py
git add astromesh/api/routes/agents.py tests/test_chain_api.py CHANGELOG.md
git commit -m "feat(api): /run dispara la cadena del agente y expone GET /agents/{n}/chain"
```

Entrada de `CHANGELOG.md` bajo `### Added (Backend)`:

```markdown
- **API**: `POST /v1/agents/{name}/run` ejecuta la cadena declarada por el agente y devuelve
  el bloque `chain` con el estado de cada eslabón (`success`, `error`, `skipped` con su
  motivo). La `answer` sigue siendo la del agente invocado, así que los clientes existentes
  no cambian. Nuevo `GET /v1/agents/{name}/chain` devuelve el grafo expandido sin ejecutar
  nada — es un artefacto de tiempo de compilación.
```

---

## Task 13: Trazas de la cadena end-to-end

**Files:**
- Test: `tests/test_chain_trace.py` (crear)
- Modify: `astromesh/workflow/__init__.py` si el test descubre que el trace no se propaga

**Interfaces:**
- Consumes: todo lo anterior.

- [ ] **Step 1: Escribir el test**

Crear `tests/test_chain_trace.py`:

```python
"""Toda la cadena tiene que colgar de un solo árbol de trazas."""

from astromesh.workflow import WorkflowEngine
from astromesh.workflow.models import StepSpec, WorkflowSpec


class _RuntimeSpy:
    def __init__(self):
        self.trazas = []
        self.sesiones = []

    async def run(self, agent_name, query, session_id, context=None, parent_trace_id=None, **kw):
        self.trazas.append(parent_trace_id)
        self.sesiones.append(session_id)
        return {"answer": f"ok {agent_name}", "steps": []}


async def test_todos_los_eslabones_comparten_trace_y_sesion():
    runtime = _RuntimeSpy()
    engine = WorkflowEngine(workflows_dir="", runtime=runtime, tool_registry=None)
    await engine.bootstrap()
    engine.register_workflow(
        WorkflowSpec(
            name="__chain__a",
            steps=[
                StepSpec(name="a", agent="a", input_template="{{ trigger.query }}"),
                StepSpec(name="a__b", agent="b", input_template="{{ steps.a.output.answer }}"),
                StepSpec(name="a__c", agent="c", input_template="{{ steps.a.output.answer }}"),
            ],
        )
    )

    await engine.run("__chain__a", trigger={"query": "hola"})

    assert len(runtime.trazas) == 3
    assert len(set(runtime.trazas)) == 1, f"trazas distintas: {runtime.trazas}"
    assert runtime.trazas[0] is not None
    assert len(set(runtime.sesiones)) == 1, f"sesiones distintas: {runtime.sesiones}"


async def test_el_resultado_trae_el_arbol_completo():
    runtime = _RuntimeSpy()
    engine = WorkflowEngine(workflows_dir="", runtime=runtime, tool_registry=None)
    await engine.bootstrap()
    engine.register_workflow(
        WorkflowSpec(
            name="__chain__a",
            steps=[
                StepSpec(name="a", agent="a", input_template="{{ trigger.query }}"),
                StepSpec(name="a__b", agent="b", input_template="x"),
            ],
        )
    )

    result = await engine.run("__chain__a", trigger={"query": "hola"})

    assert result.trace
    nombres = [s.get("name", "") for s in result.trace.get("spans", [])]
    assert any("step.a" in n for n in nombres)
    assert any("step.a__b" in n for n in nombres)
```

- [ ] **Step 2: Correr el test**

```bash
uv run pytest tests/test_chain_trace.py -v
```

Si `test_el_resultado_trae_el_arbol_completo` falla por la forma de `tracing.to_dict()`, ajustar el test a la estructura real que devuelve `TracingContext.to_dict()` — leer `astromesh/observability/tracing.py` para confirmar la clave (`spans` u otra) y el nombre de cada span.

- [ ] **Step 3: Arreglar lo que haga falta**

Si el primer test falla, revisar que la Task 2 haya quedado aplicada: el executor por-corrida de `_drive` tiene que recibir `parent_trace_id=tracing.trace_id` y `session_id=run.run_id`.

- [ ] **Step 4: Lint y commit**

```bash
uv run ruff format astromesh/ tests/test_chain_trace.py
uv run ruff check astromesh/ tests/test_chain_trace.py
git add astromesh/ tests/test_chain_trace.py
git commit -m "test: la cadena completa cuelga de un solo árbol de trazas"
```

---

## Task 14: Ejemplos, documentación y arreglo del workflow roto

**Files:**
- Modify: `config/workflows/example.workflow.yaml`
- Modify: `config/agents/sales-qualifier.agent.yaml`
- Create: `docs/agent-chaining.md`
- Modify: `CHANGELOG.md`
- Test: `tests/test_chain_examples.py` (crear)

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_chain_examples.py`:

```python
"""Los ejemplos versionados tienen que cargar y compilar de verdad."""

from pathlib import Path

import yaml

from astromesh.chain.compiler import compile_chain
from astromesh.chain.output import normalize_output_schema
from astromesh.workflow.loader import WorkflowLoader

RAIZ = Path(__file__).resolve().parents[1]


def _cargar_agentes():
    configs = {}
    for f in (RAIZ / "config" / "agents").glob("*.agent.yaml"):
        raw = yaml.safe_load(f.read_text(encoding="utf-8"))
        configs[raw["metadata"]["name"]] = raw
    return configs


def test_el_workflow_de_ejemplo_carga():
    ruta = RAIZ / "config" / "workflows" / "example.workflow.yaml"
    wf = WorkflowLoader(str(ruta.parent)).load_file(ruta)
    assert wf.name == "lead-qualification"


def test_todas_las_cadenas_de_config_compilan():
    """Si un ejemplo tiene un ciclo o apunta a un agente que no existe, acá se ve."""
    configs = _cargar_agentes()
    for nombre in configs:
        compile_chain(nombre, configs)  # no debe levantar


def test_sales_qualifier_declara_score_en_su_output_schema():
    configs = _cargar_agentes()
    schema = normalize_output_schema(configs["sales-qualifier"]["spec"].get("output_schema"))
    assert schema is not None, "el ejemplo de la doc depende de que declare output_schema"
    assert "score" in schema["properties"]


def test_el_when_del_workflow_de_ejemplo_referencia_un_campo_declarado():
    """El `when` versionado apuntaba a output.data.score sin que `data` existiera:
    con _SilentUndefined rendía vacío y caía al default en silencio."""
    ruta = RAIZ / "config" / "workflows" / "example.workflow.yaml"
    wf = WorkflowLoader(str(ruta.parent)).load_file(ruta)
    configs = _cargar_agentes()
    schema = normalize_output_schema(configs["sales-qualifier"]["spec"].get("output_schema"))

    switches = [s for s in wf.steps if s.switch]
    condiciones = [b.get("when", "") for s in switches for b in s.switch if b.get("when")]
    assert condiciones, "el ejemplo tenía un switch condicional"
    for cond in condiciones:
        if "output.data." in cond:
            campo = cond.split("output.data.")[1].split()[0].strip(" }")
            assert campo in schema["properties"], (
                f"el `when` referencia '{campo}', que sales-qualifier no declara"
            )
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
uv run pytest tests/test_chain_examples.py -v
```

Esperado: `test_sales_qualifier_declara_score_en_su_output_schema` FALLA — el agente no declara `output_schema` todavía.

- [ ] **Step 3: Agregar `output_schema` y `chain` al agente de ejemplo**

En `config/agents/sales-qualifier.agent.yaml`, agregar bajo `spec:` (después del bloque `prompts:`):

```yaml
  output_schema:
    score:
      type: integer
    urgent:
      type: boolean
    next_action:
      type: string
```

y al final del `spec:`:

```yaml
  chain:
    mode: sequential
    on_complete:
      # Un lead caliente arranca el contacto de una.
      - agent: email-composer
        when: "{{ output.data.score > 7 }}"
        input: "{{ output.answer }}"
        retry:
          max_attempts: 3
          backoff: exponential
        timeout_seconds: 30
        on_error: continue
```

**`email-composer` no existe en `config/agents/`**, así que hay que crearlo o la compilación falla al arrancar — que es exactamente lo que el test comprueba. Crear `config/agents/email-composer.agent.yaml`:

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: email-composer
  version: "1.0.0"
  namespace: sales

spec:
  identity:
    display_name: "Email Composer"
    description: "Redacta el primer contacto para un lead ya calificado"

  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"
      endpoint: "http://localhost:11434"
      parameters:
        temperature: 0.4
        max_tokens: 1024

  prompts:
    system: |
      Redactás el primer email de contacto a un lead ya calificado.
      Recibís la calificación completa. Escribí un email breve, concreto
      y sin relleno, que abra la conversación en vez de cerrarla.

  orchestration:
    pattern: react
    max_iterations: 3
    timeout_seconds: 60
```

`config/workflows/example.workflow.yaml` ya referenciaba este agente sin que existiera, así que crearlo cierra las dos puntas.

- [ ] **Step 4: Arreglar el workflow de ejemplo**

En `config/workflows/example.workflow.yaml`, el `when` sigue siendo `{{ steps.qualify.output.data.score > 7 }}`. Ahora que `sales-qualifier` declara `score` en su `output_schema`, esa condición **sí** puede dar true. Verificar que el nombre del campo coincida exactamente con el declarado y agregar el comentario:

```yaml
    - name: decide
      switch:
        # `data` lo puebla el output_schema de sales-qualifier; sin él esta
        # condición rendía vacío y caía al default sin decir nada.
        - when: "{{ steps.qualify.output.data.score > 7 }}"
          goto: notify
        - default: true
          goto: log-and-skip
```

- [ ] **Step 5: Escribir la documentación**

Crear `docs/agent-chaining.md` cubriendo, con ejemplos ejecutables:

1. Qué problema resuelve y en qué se diferencia de escribir un `kind: Workflow`
2. El YAML completo de `spec.chain` con todos los campos
3. Semántica de las reglas: disparan todas las que matcheen; `default` sólo si ningún `when` matcheó; las reglas sin `when` no cuentan como match
4. `mode: sequential` vs `parallel`, y **cuándo se evalúan las guardas en cada uno** (en `parallel`, todas antes de arrancar cualquier rama; un `when` que mire a un hermano se rechaza en bootstrap)
5. `input` por defecto: `{{ output.answer }}`
6. Tabla del contexto disponible en `when` e `input`
7. `spec.output_schema`: taquigrafía, bloque ```json, `data`/`data_error`, y la lista de keywords de JSON Schema que el validador ignora
8. Manejo de errores: `retry`, `timeout_seconds`, `on_error: stop|continue|<agente>`
9. Recursión, `max_depth`, ciclos — y que todo eso explota al arrancar, no en runtime
10. La forma de la respuesta con el bloque `chain`
11. `GET /v1/agents/{name}/chain`
12. Fuera de alcance: fire-and-forget asíncrono, reintento por JSON inválido, cadenas entre nodos, `when_llm`

**No** crear páginas en `docs-site/`: el sitio público se actualiza recién cuando la feature sale en un release.

- [ ] **Step 6: Correr toda la suite**

```bash
uv run pytest -v
uv run ruff check astromesh/ tests/
uv run ruff format --check astromesh/ tests/
```

Esperado: **todo** PASS y lint limpio.

- [ ] **Step 7: Commit**

```bash
git add config/ docs/agent-chaining.md tests/test_chain_examples.py CHANGELOG.md
git commit -m "docs: guía de encadenamiento de agentes y ejemplos que compilan

Arregla además el `when` de example.workflow.yaml, que referenciaba
output.data.score sin que ningún agente declarara `data`: con
_SilentUndefined rendía vacío y caía al default en silencio."
```

Entrada de `CHANGELOG.md` bajo `### Fixed`:

```markdown
- **Ejemplos**: el `when` de `config/workflows/example.workflow.yaml` referenciaba
  `output.data.score` sin que ningún agente declarara `data`, así que nunca podía dar
  verdadero y —por `_SilentUndefined`— caía al `default` sin señalar el problema.
  `sales-qualifier` ahora declara ese campo en su `output_schema`.
```

---

## Verificación final

Antes de dar el trabajo por terminado:

```bash
uv run pytest -v                          # toda la suite
uv run ruff check astromesh/ tests/       # lint
uv run ruff format --check astromesh/ tests/
uv run pytest --cov=astromesh --cov-report=term-missing -k chain
```

Comprobaciones manuales de compatibilidad hacia atrás:

- [ ] `POST /v1/agents/support-agent/run` (sin `chain`) devuelve `chain: null` y `data: null`, y el resto de la forma es idéntica a la de antes del cambio
- [ ] un `*.workflow.yaml` sin `when`, sin `parallel` y sin `strict_conditions` se comporta igual que antes
- [ ] `uv run python -c "import astromesh.api.main"` funciona **sin extras instalados** (la restricción de la imagen de astromesh-os)
- [ ] `git diff --stat main -- pyproject.toml uv.lock` está vacío: no se agregaron dependencias ni se bumpeó versión
