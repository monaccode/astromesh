# Astromesh v0.36.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corregir tres defectos del runtime que bloquean la operación de Astromesh como
servicio administrado por API: RAG que se pierde al arrancar sin agentes en disco,
registro de templates de prompt sin alcance, y consumo de modelos que no se puede
atribuir.

**Architecture:** Los tres cambios son quirúrgicos y aislados entre sí. A1 reordena dos
líneas de `bootstrap()`. A2 le agrega una clave de alcance al diccionario de templates de
`PromptEngine`. A3 enriquece `usage_from_trace` —la función que ya comparten `/run` y el
WebSocket— para que agrupe el consumo por proveedor+modelo+rol, leyendo atributos de span
que el runtime **ya escribe**. Ninguno introduce dependencias nuevas ni cambia la forma en
que se despliegan los agentes.

**Tech Stack:** Python 3.12+, uv, pytest (`asyncio_mode = "auto"`), Pydantic v2, ruff.

## Global Constraints

- **Compatibilidad hacia atrás obligatoria.** `usage.tokens_in`, `usage.tokens_out` y
  `usage.model` deben seguir existiendo con el mismo significado de totales. Los
  consumidores actuales (Cortex, Orbit, el tablero del node) no se pueden romper.
- **Ningún cambio a la forma en que se declaran los agentes.** El esquema
  `astromesh/v1` no se toca en este release.
- **`prompts.templates` no se conecta.** A2 le da alcance al registro; darle uso es una
  función nueva y queda explícitamente fuera de alcance.
- **Line length 100**, target `py312`. `uv run ruff check astromesh/ tests/` y
  `uv run ruff format astromesh/ tests/` deben pasar limpios.
- **Regla de changelog (CLAUDE.md):** todo commit `feat:`, `fix:` o `refactor:` lleva su
  entrada en `CHANGELOG.md` bajo `## [Unreleased]` en el **mismo commit**.
- **Rama de trabajo:** `develop` (rama principal del repo). No hacer push salvo pedido
  explícito.
- **`[Unreleased]` ya tiene contenido** (los arreglos de `parameters` de v0.35.x sin
  taggear). La Task 6 lo mueve entero a la sección `v0.36.0`, no solo lo de este plan.

---

## File Structure

| Archivo | Responsabilidad | Tarea |
|---|---|---|
| `astromesh/runtime/engine.py` | Reordenar la carga de RAG en `bootstrap()`; pasar el alcance al registrar templates | 1, 2 |
| `astromesh/core/prompt_engine.py` | Alcance por agente en el registro de templates | 2 |
| `astromesh/api/usage.py` | Agregación de consumo desde el trace: total y desglose por modelo | 3, 4 |
| `astromesh/api/routes/agents.py` | Modelos Pydantic de la respuesta: `ModelUsage`, `UsageInfo.by_model` | 5 |
| `tests/test_engine_bootstrap_empty.py` | **Nuevo.** Runtime sin agentes en disco | 1 |
| `tests/test_prompt_engine.py` | Alcance de templates | 2 |
| `tests/test_usage_from_trace.py` | Modelo real y desglose por modelo | 3, 4 |
| `tests/test_agents_run_usage.py` | **Nuevo.** El desglose llega a la respuesta HTTP | 5 |
| `CHANGELOG.md`, `pyproject.toml`, `astromesh/__init__.py` | Release | 6 |

---

## Task 1: A1 — RAG sobrevive a un runtime sin agentes en disco

**Files:**
- Modify: `astromesh/runtime/engine.py:341-372` (método `bootstrap`)
- Test: `tests/test_engine_bootstrap_empty.py` (nuevo)

**Interfaces:**
- Consumes: nada de tareas previas.
- Produces: nada que otras tareas consuman. `AgentRuntime._rag_specs` pasa a estar
  poblado aunque no exista `config/agents/`.

**Contexto para quien implementa:** `bootstrap()` sale temprano cuando no existe el
directorio de agentes, y esa salida ocurre **antes** de cargar los pipelines de RAG. Un
runtime que arranca vacío y recibe agentes por API se queda sin RAG para siempre.
`RAGPipelineLoader.load_all()` ya tolera un directorio inexistente (devuelve `{}`), así
que moverlo hacia arriba es seguro.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_engine_bootstrap_empty.py`:

```python
"""Un runtime sin agentes en disco se administra por API: no debe perder capacidades."""

from astromesh.runtime.engine import AgentRuntime

RAG_YAML = """
apiVersion: astromesh/v1
kind: RAGPipeline
metadata:
  name: product-knowledge
spec:
  chunking: {strategy: recursive, chunk_size: 512}
  embeddings: {provider: ollama, model: nomic-embed-text}
  vector_store: {backend: pgvector, collection: docs}
  reranking: {enabled: false}
  retrieval: {top_k: 5}
"""


async def test_rag_specs_load_when_agents_dir_is_absent(tmp_path):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    (rag_dir / "pk.rag.yaml").write_text(RAG_YAML)
    # Sin directorio 'agents': es el modo que usa un runtime administrado por API.

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    assert "product-knowledge" in runtime._rag_specs
    assert runtime.list_agents() == []


async def test_rag_specs_load_when_agents_dir_is_empty(tmp_path):
    (tmp_path / "agents").mkdir()
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    (rag_dir / "pk.rag.yaml").write_text(RAG_YAML)

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    assert "product-knowledge" in runtime._rag_specs
    assert runtime.list_agents() == []
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_engine_bootstrap_empty.py -v`

Expected: `test_rag_specs_load_when_agents_dir_is_absent` FALLA con
`AssertionError: assert 'product-knowledge' in {}`.
`test_rag_specs_load_when_agents_dir_is_empty` PASA (ese camino ya funciona) — se incluye
como red de seguridad para no romperlo al reordenar.

- [ ] **Step 3: Reordenar `bootstrap()`**

En `astromesh/runtime/engine.py`, dentro de `bootstrap()`, reemplazar:

```python
        agents_dir = self._config_dir / "agents"
        if not agents_dir.exists():
            return
        from astromesh.rag.loader import RAGPipelineLoader

        self._rag_specs = RAGPipelineLoader(str(self._config_dir / "rag")).load_all()
        configs = []
```

por:

```python
        # RAG antes de la salida temprana: un runtime que se administra por API arranca
        # sin agentes en disco, y hasta v0.35.1 eso lo dejaba con _rag_specs vacío para
        # siempre — los agentes registrados después no podían resolver su base de
        # conocimiento. load_all() ya tolera un directorio inexistente.
        from astromesh.rag.loader import RAGPipelineLoader

        self._rag_specs = RAGPipelineLoader(str(self._config_dir / "rag")).load_all()

        agents_dir = self._config_dir / "agents"
        if not agents_dir.exists():
            return
        configs = []
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_engine_bootstrap_empty.py -v`
Expected: 2 passed.

Run: `uv run pytest tests/ -k "rag or engine" -q`
Expected: sin fallos nuevos respecto de la línea base.

- [ ] **Step 5: Entrada de changelog**

En `CHANGELOG.md`, bajo `## [Unreleased]`, agregar una subsección `### Fixed (Core)` si no
existe ya, y dentro:

```markdown
- **Los pipelines de RAG ya no se pierden cuando el runtime arranca sin agentes en disco.**
  `bootstrap()` salía temprano al no encontrar `config/agents/`, y esa salida ocurría antes
  de cargar `config/rag/*.rag.yaml`. Un runtime administrado por API —que arranca vacío y
  recibe sus agentes por `POST /v1/agents`— quedaba con `_rag_specs` vacío de forma
  permanente, así que ningún agente registrado después podía resolver su `knowledge_base`.
  La carga de RAG ahora ocurre antes de esa salida.
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_engine_bootstrap_empty.py astromesh/runtime/engine.py CHANGELOG.md
git commit -m "fix(runtime): cargar los specs de RAG aunque no haya agentes en disco"
```

---

## Task 2: A2 — Alcance por agente en el registro de templates

**Files:**
- Modify: `astromesh/core/prompt_engine.py` (completo, 30 líneas)
- Modify: `astromesh/runtime/engine.py:588-589` (dentro de `_build_agent`)
- Test: `tests/test_prompt_engine.py` (agregar casos)

**Interfaces:**
- Consumes: nada de tareas previas.
- Produces: `PromptEngine.register_template(name, template_str, scope=None)` y
  `PromptEngine.render_template(name, variables, scope=None)`. `scope=None` conserva el
  comportamiento global previo.

**Contexto para quien implementa:** `PromptEngine` es una única instancia compartida por
todo el runtime (`engine.py:336`), y `_build_agent` registra los templates de cada agente
por nombre pelado. Dos agentes con un template homónimo se pisan. Hoy **ningún camino de
producción lee esos templates** —el agente renderiza su prompt de sistema con `render()`
sobre el string crudo— así que el defecto es latente. Se cierra igual porque el diseño de
pool compartido multi-tenant apuesta a que el runtime no tiene registros globales
mutables con clave por nombre.

**No conectar la función.** No agregar llamadas a `render_template` en ningún camino de
ejecución: eso es una función nueva, no esta corrección.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_prompt_engine.py`:

```python
def test_templates_are_isolated_by_scope():
    engine = PromptEngine()
    engine.register_template("greeting", "Hola {{ user }} desde ventas", scope="ventas")
    engine.register_template("greeting", "Hola {{ user }} desde soporte", scope="soporte")

    assert engine.render_template("greeting", {"user": "Ana"}, scope="ventas") == (
        "Hola Ana desde ventas"
    )
    assert engine.render_template("greeting", {"user": "Ana"}, scope="soporte") == (
        "Hola Ana desde soporte"
    )


def test_scoped_template_is_not_visible_without_its_scope():
    engine = PromptEngine()
    engine.register_template("greeting", "Hola {{ user }}", scope="ventas")

    assert engine.render_template("greeting", {"user": "Ana"}) == ""


def test_unscoped_templates_keep_working():
    engine = PromptEngine()
    engine.register_template("greeting", "Hola {{ user }}")

    assert engine.render_template("greeting", {"user": "Ana"}) == "Hola Ana"
    assert engine.render_template("greeting", {"user": "Ana"}, scope="ventas") == ""
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_prompt_engine.py -v`

Expected: los tres nuevos FALLAN con
`TypeError: register_template() got an unexpected keyword argument 'scope'`.

- [ ] **Step 3: Implementar el alcance en `PromptEngine`**

En `astromesh/core/prompt_engine.py`, reemplazar la clase `PromptEngine` completa por:

```python
class PromptEngine:
    def __init__(self):
        self._env = Environment(loader=BaseLoader(), undefined=SilentUndefined)
        # Clave por (scope, name). El scope es el nombre del agente dueño del template,
        # o None para los globales. Sin él, dos agentes con un template homónimo se
        # pisaban en silencio — inaceptable en un runtime que sirve a varios tenants.
        self._templates: dict[tuple[str | None, str], str] = {}

    def render(self, template_str, variables):
        return self._env.from_string(template_str).render(**variables)

    def register_template(self, name, template_str, scope=None):
        self._templates[(scope, name)] = template_str

    def render_template(self, name, variables, scope=None):
        template_str = self._templates.get((scope, name))
        if not template_str:
            return ""
        return self.render(template_str, variables)
```

- [ ] **Step 4: Pasar el alcance desde `_build_agent`**

En `astromesh/runtime/engine.py`, dentro de `_build_agent`, reemplazar:

```python
        for name, tmpl in prompts.get("templates", {}).items():
            self._prompt_engine.register_template(name, tmpl)
```

por:

```python
        for name, tmpl in prompts.get("templates", {}).items():
            self._prompt_engine.register_template(name, tmpl, scope=metadata["name"])
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_prompt_engine.py -v`
Expected: todos pasan, incluidos `test_register_and_render_template` y
`test_render_nonexistent_template` que ya existían.

Run: `uv run pytest tests/ -q`
Expected: sin fallos nuevos respecto de la línea base.

- [ ] **Step 6: Entrada de changelog**

En `CHANGELOG.md`, bajo `## [Unreleased]` → `### Fixed (Core)`:

```markdown
- **Los templates de prompt de un agente ya no pisan los de otro.** `PromptEngine` es una
  única instancia compartida por el runtime y `_build_agent` registraba los
  `prompts.templates` de cada agente por nombre pelado: dos agentes que declararan un
  template homónimo colisionaban, y ganaba el último construido. El registro ahora lleva
  el nombre del agente como alcance. Defecto latente —ningún camino de ejecución lee hoy
  esos templates— cerrado antes de que un runtime multi-agente lo vuelva alcanzable.
```

- [ ] **Step 7: Commit**

```bash
git add astromesh/core/prompt_engine.py astromesh/runtime/engine.py \
        tests/test_prompt_engine.py CHANGELOG.md
git commit -m "fix(core): dar alcance por agente al registro de templates de prompt"
```

---

## Task 3: A3.1 — El campo `model` deja de volver vacío

**Files:**
- Modify: `astromesh/api/usage.py:24-45`
- Test: `tests/test_usage_from_trace.py` (agregar casos)

**Interfaces:**
- Consumes: nada de tareas previas.
- Produces: `usage_from_trace(trace)` sigue devolviendo
  `{"tokens_in": int, "tokens_out": int, "model": str}` o `None`. Cambia solo **de dónde**
  sale `model`. La Task 4 le agrega la clave `by_model`.

**Contexto para quien implementa:** `usage_from_trace` lee el modelo únicamente de
`attributes.metadata.model`, que es la rama heredada de proveedores externos. El runtime
lo escribe como atributo **directo** del span (`engine.py:846`,
`llm_span.set_attribute("model", response.model)`). Resultado: con proveedores nativos el
campo vuelve siempre vacío, incluso en una corrida de un solo modelo. Verificado en la
prueba de humo del 2026-07-20, donde la respuesta trajo `"model": ""`.

Criterio: se conserva la semántica documentada de "primer modelo visto", y el atributo
directo tiene prioridad sobre el heredado.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_usage_from_trace.py`:

```python
def test_reads_model_from_direct_span_attribute():
    """El runtime escribe el modelo como atributo directo, no bajo metadata."""
    trace = {
        "spans": [
            {
                "attributes": {
                    "model": "gpt-4o-mini",
                    "provider": "openai",
                    "input_tokens": 10,
                    "output_tokens": 4,
                }
            }
        ]
    }
    assert usage_from_trace(trace) == {
        "tokens_in": 10,
        "tokens_out": 4,
        "model": "gpt-4o-mini",
    }


def test_direct_model_attribute_wins_over_legacy_metadata():
    trace = {
        "spans": [
            {
                "attributes": {
                    "model": "directo",
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "metadata": {"model": "heredado"},
                }
            }
        ]
    }
    assert usage_from_trace(trace)["model"] == "directo"


def test_first_model_wins_across_spans():
    trace = {
        "spans": [
            {"attributes": {"model": "primero", "input_tokens": 1, "output_tokens": 1}},
            {"attributes": {"model": "segundo", "input_tokens": 1, "output_tokens": 1}},
        ]
    }
    assert usage_from_trace(trace)["model"] == "primero"
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_usage_from_trace.py -v`

Expected: los tres nuevos FALLAN — `model` vuelve `""` en lugar del valor esperado.

- [ ] **Step 3: Leer el atributo directo**

En `astromesh/api/usage.py`, dentro del bucle `for span in spans:`, reemplazar:

```python
        # Legacy / external providers nest them under metadata.usage.
        span_meta = attrs.get("metadata", {})
        if isinstance(span_meta, dict) and "usage" in span_meta:
            u = span_meta["usage"]
            total_in += u.get("prompt_tokens", 0)
            total_out += u.get("completion_tokens", 0)
        if isinstance(span_meta, dict) and "model" in span_meta and not model_used:
            model_used = span_meta["model"]
```

por:

```python
        # El runtime escribe el modelo como atributo directo del span llm.complete
        # (engine.py, llm_span.set_attribute("model", response.model)). Hasta v0.35.1
        # esto solo se leía de metadata.model —la rama heredada— así que con proveedores
        # nativos el campo volvía siempre vacío.
        if not model_used and isinstance(attrs.get("model"), str):
            model_used = attrs["model"]

        # Legacy / external providers nest them under metadata.usage.
        span_meta = attrs.get("metadata", {})
        if isinstance(span_meta, dict) and "usage" in span_meta:
            u = span_meta["usage"]
            total_in += u.get("prompt_tokens", 0)
            total_out += u.get("completion_tokens", 0)
        if isinstance(span_meta, dict) and "model" in span_meta and not model_used:
            model_used = span_meta["model"]
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_usage_from_trace.py -v`
Expected: todos pasan, incluidos los cuatro que ya existían.

- [ ] **Step 5: Entrada de changelog**

En `CHANGELOG.md`, bajo `## [Unreleased]` → `### Fixed (Core)`:

```markdown
- **`usage.model` ya no vuelve vacío con proveedores nativos.** `usage_from_trace` leía el
  modelo solo de `metadata.model` —la forma que usan los proveedores externos heredados—
  mientras que el runtime lo escribe como atributo directo del span `llm.complete`. Toda
  corrida sobre un proveedor nativo reportaba `"model": ""`, en `POST /v1/agents/{n}/run`
  y en el WebSocket por igual. Ahora se lee el atributo directo, con prioridad sobre el
  heredado.
```

- [ ] **Step 6: Commit**

```bash
git add astromesh/api/usage.py tests/test_usage_from_trace.py CHANGELOG.md
git commit -m "fix(api): leer el modelo del atributo directo del span en usage_from_trace"
```

---

## Task 4: A3.2 — Desglose de consumo por modelo

**Files:**
- Modify: `astromesh/api/usage.py` (docstrings y cuerpo de `usage_from_trace`)
- Test: `tests/test_usage_from_trace.py` (agregar casos)

**Interfaces:**
- Consumes: `usage_from_trace` con el arreglo de la Task 3.
- Produces: `usage_from_trace(trace)` devuelve además la clave `by_model`: una lista de
  diccionarios `{"provider": str, "model": str, "role": str, "calls": int,
  "tokens_in": int, "tokens_out": int, "cost": float}`, ordenada de mayor a menor por
  `tokens_in + tokens_out` y, a igualdad, alfabéticamente por `model`. La Task 5 la expone
  en la respuesta HTTP.

**Contexto para quien implementa:** Una sola corrida puede tocar varios modelos: por el
patrón de orquestación (`supervisor`, `pipeline`, `swarm`, `parallel_fan_out`), por el
enrutamiento por rol, y por el fallback entre proveedores. El campo plano `model` no puede
representar eso. Los atributos necesarios ya están en cada span `llm.complete`: `model`,
`provider`, `resolved_role`, `input_tokens`, `output_tokens`, `cost`.

Reglas de agrupación:
- La clave es la terna `(provider, model, role)`.
- `role` sale de `resolved_role`; si falta, de `role`; si falta, `"default"`.
- Solo se cuentan como llamada los spans que traen un `model` no vacío. Un span sin modelo
  puede aportar tokens al total (rama heredada) pero no crea una fila de desglose.
- `usage_from_trace` **nunca lanza**: el trace es dato del runtime, no un contrato
  validado. Un `cost` no numérico se ignora, no rompe.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_usage_from_trace.py`:

```python
def test_by_model_groups_by_provider_model_and_role():
    trace = {
        "spans": [
            {
                "attributes": {
                    "model": "gpt-4o",
                    "provider": "openai",
                    "resolved_role": "reasoning",
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cost": 0.5,
                }
            },
            {
                "attributes": {
                    "model": "gpt-4o",
                    "provider": "openai",
                    "resolved_role": "reasoning",
                    "input_tokens": 50,
                    "output_tokens": 10,
                    "cost": 0.25,
                }
            },
            {
                "attributes": {
                    "model": "centinela-4b",
                    "provider": "ollama",
                    "resolved_role": "classification",
                    "input_tokens": 30,
                    "output_tokens": 5,
                    "cost": 0.0,
                }
            },
        ]
    }
    usage = usage_from_trace(trace)

    assert usage["tokens_in"] == 180
    assert usage["tokens_out"] == 35
    assert usage["by_model"] == [
        {
            "provider": "openai",
            "model": "gpt-4o",
            "role": "reasoning",
            "calls": 2,
            "tokens_in": 150,
            "tokens_out": 30,
            "cost": 0.75,
        },
        {
            "provider": "ollama",
            "model": "centinela-4b",
            "role": "classification",
            "calls": 1,
            "tokens_in": 30,
            "tokens_out": 5,
            "cost": 0.0,
        },
    ]


def test_same_model_under_different_roles_are_separate_rows():
    trace = {
        "spans": [
            {
                "attributes": {
                    "model": "gpt-4o-mini",
                    "provider": "openai",
                    "resolved_role": "reasoning",
                    "input_tokens": 10,
                    "output_tokens": 2,
                }
            },
            {
                "attributes": {
                    "model": "gpt-4o-mini",
                    "provider": "openai",
                    "resolved_role": "summarization",
                    "input_tokens": 8,
                    "output_tokens": 1,
                }
            },
        ]
    }
    rows = usage_from_trace(trace)["by_model"]
    assert len(rows) == 2
    assert {r["role"] for r in rows} == {"reasoning", "summarization"}


def test_role_defaults_when_absent():
    trace = {
        "spans": [
            {"attributes": {"model": "m", "provider": "p", "input_tokens": 1, "output_tokens": 1}}
        ]
    }
    assert usage_from_trace(trace)["by_model"][0]["role"] == "default"


def test_falls_back_to_role_when_resolved_role_missing():
    trace = {
        "spans": [
            {
                "attributes": {
                    "model": "m",
                    "provider": "p",
                    "role": "classification",
                    "input_tokens": 1,
                    "output_tokens": 1,
                }
            }
        ]
    }
    assert usage_from_trace(trace)["by_model"][0]["role"] == "classification"


def test_spans_without_model_contribute_tokens_but_no_row():
    trace = {
        "spans": [
            {"attributes": {"input_tokens": 7, "output_tokens": 3}},
            {"attributes": {"model": "m", "provider": "p", "input_tokens": 1, "output_tokens": 1}},
        ]
    }
    usage = usage_from_trace(trace)
    assert usage["tokens_in"] == 8
    assert len(usage["by_model"]) == 1


def test_non_numeric_cost_is_ignored_not_fatal():
    trace = {
        "spans": [
            {
                "attributes": {
                    "model": "m",
                    "provider": "p",
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cost": "no-es-un-numero",
                }
            }
        ]
    }
    assert usage_from_trace(trace)["by_model"][0]["cost"] == 0.0


def test_legacy_only_trace_reports_empty_by_model():
    trace = {
        "spans": [
            {"attributes": {"metadata": {"usage": {"prompt_tokens": 4, "completion_tokens": 6}}}}
        ]
    }
    usage = usage_from_trace(trace)
    assert usage["tokens_in"] == 4
    assert usage["by_model"] == []
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_usage_from_trace.py -v`

Expected: los siete nuevos FALLAN con `KeyError: 'by_model'`.

- [ ] **Step 3: Implementar el desglose**

En `astromesh/api/usage.py`, reemplazar el archivo completo por:

```python
"""Token usage derived from a run's trace.

Both POST /v1/agents/{name}/run and the WebSocket handler report usage, and both
derive it the same way: walk the trace's spans and sum what the providers
reported. It lives here so the two can't drift — the legacy metadata.usage
branch below is exactly the kind of detail that gets fixed in one copy and
forgotten in the other.

A single run routinely touches more than one model: orchestration patterns that
consult several (supervisor, pipeline, swarm, parallel_fan_out), per-role model
routing, and provider fallback. The flat `model` field cannot represent that, so
`by_model` carries the breakdown — grouped by (provider, model, role), which is
what a cost attribution needs.
"""


def _as_float(value) -> float:
    """A trace is data from the runtime, not a validated contract: never raise."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def _as_int(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def usage_from_trace(trace: dict | None) -> dict | None:
    """Sum token usage across a trace's spans.

    Returns {"tokens_in", "tokens_out", "model", "by_model"}, or None when the
    trace reports no tokens at all (a run that never reached a provider, or a
    malformed trace). Never raises.

    `model` is the first model seen, kept for backward compatibility; it has no
    correct value on a multi-model run. `by_model` is the authoritative
    breakdown: one entry per (provider, model, role), ordered by total tokens
    descending, then by model name.
    """
    spans = trace.get("spans", []) if isinstance(trace, dict) else []
    if not isinstance(spans, list):
        return None

    total_in = 0
    total_out = 0
    model_used = ""
    breakdown: dict[tuple[str, str, str], dict] = {}

    for span in spans:
        attrs = span.get("attributes", {}) if isinstance(span, dict) else {}
        if not isinstance(attrs, dict):
            continue

        # The runtime stores tokens as input_tokens / output_tokens.
        span_in = _as_int(attrs.get("input_tokens", 0))
        span_out = _as_int(attrs.get("output_tokens", 0))
        total_in += span_in
        total_out += span_out

        # El runtime escribe el modelo como atributo directo del span llm.complete
        # (engine.py, llm_span.set_attribute("model", response.model)). Hasta v0.35.1
        # esto solo se leía de metadata.model —la rama heredada— así que con proveedores
        # nativos el campo volvía siempre vacío.
        model = attrs.get("model")
        if isinstance(model, str) and model:
            if not model_used:
                model_used = model
            provider = attrs.get("provider")
            provider = provider if isinstance(provider, str) else ""
            role = attrs.get("resolved_role") or attrs.get("role") or "default"
            role = role if isinstance(role, str) else "default"

            key = (provider, model, role)
            entry = breakdown.get(key)
            if entry is None:
                entry = {
                    "provider": provider,
                    "model": model,
                    "role": role,
                    "calls": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "cost": 0.0,
                }
                breakdown[key] = entry
            entry["calls"] += 1
            entry["tokens_in"] += span_in
            entry["tokens_out"] += span_out
            entry["cost"] += _as_float(attrs.get("cost"))

        # Legacy / external providers nest them under metadata.usage.
        span_meta = attrs.get("metadata", {})
        if isinstance(span_meta, dict) and "usage" in span_meta:
            u = span_meta["usage"]
            total_in += u.get("prompt_tokens", 0)
            total_out += u.get("completion_tokens", 0)
        if isinstance(span_meta, dict) and "model" in span_meta and not model_used:
            model_used = span_meta["model"]

    if total_in or total_out:
        by_model = sorted(
            breakdown.values(),
            key=lambda e: (-(e["tokens_in"] + e["tokens_out"]), e["model"]),
        )
        return {
            "tokens_in": total_in,
            "tokens_out": total_out,
            "model": model_used,
            "by_model": by_model,
        }
    return None
```

- [ ] **Step 4: Actualizar los cuatro tests preexistentes**

Tres de los tests originales de `tests/test_usage_from_trace.py` comparan el diccionario
completo con `==` y fallan porque falta `by_model`. Ninguno de esos traces trae un
atributo `model` directo —todos usan la rama heredada `metadata.model`— así que en los
tres el desglose correcto es la lista vacía.

En `test_sums_input_and_output_tokens_across_spans` (línea 13):

```python
    assert usage_from_trace(trace) == {
        "tokens_in": 13,
        "tokens_out": 12,
        "model": "",
        "by_model": [],
    }
```

En `test_reads_legacy_nested_metadata_usage` (línea 29):

```python
    assert usage_from_trace(trace) == {
        "tokens_in": 4,
        "tokens_out": 6,
        "model": "gpt-4o-mini",
        "by_model": [],
    }
```

En `test_adds_direct_and_legacy_tokens_from_the_same_span` (línea 54):

```python
    assert usage_from_trace(trace) == {
        "tokens_in": 11,
        "tokens_out": 7,
        "model": "",
        "by_model": [],
    }
```

`test_takes_the_first_model_it_sees` solo indexa `["model"]`, así que no se toca. Los tres
tests de `None` y el de traces malformados tampoco.

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_usage_from_trace.py -v`
Expected: todos pasan.

Run: `uv run pytest tests/ -q`
Expected: sin fallos nuevos respecto de la línea base.

- [ ] **Step 6: Entrada de changelog**

En `CHANGELOG.md`, bajo `## [Unreleased]`, crear `### Added (Core)` si no existe:

```markdown
- **`usage.by_model`: desglose de consumo por modelo en cada corrida.** Una sola
  invocación toca habitualmente varios modelos —patrones que consultan a más de uno
  (supervisor, pipeline, swarm, parallel_fan_out), enrutamiento por rol, y fallback entre
  proveedores— y el campo plano `usage.model` no tiene un valor correcto posible en ese
  caso. `usage_from_trace` ahora agrupa el consumo por `(provider, model, role)` y reporta
  `calls`, `tokens_in`, `tokens_out` y `cost` de cada uno, ordenado por consumo
  descendente. Los campos planos se conservan como totales. Lo reciben por igual
  `POST /v1/agents/{n}/run` y el WebSocket, que ya compartían la función.
```

- [ ] **Step 7: Commit**

```bash
git add astromesh/api/usage.py tests/test_usage_from_trace.py CHANGELOG.md
git commit -m "feat(api): desglosar el consumo por modelo en usage_from_trace"
```

---

## Task 5: A3.3 — Exponer el desglose en la respuesta HTTP

**Files:**
- Modify: `astromesh/api/routes/agents.py:45-48` (modelos Pydantic)
- Test: `tests/test_agents_run_usage.py` (nuevo)

**Interfaces:**
- Consumes: `usage_from_trace` con la clave `by_model` de la Task 4.
- Produces: `AgentRunResponse.usage.by_model` como lista de `ModelUsage` en el JSON de
  `POST /v1/agents/{name}/run`.

**Contexto para quien implementa:** `UsageInfo` es un modelo Pydantic estricto; la ruta lo
construye con `UsageInfo(**usage_data)`. Sin declarar el campo, Pydantic **descarta**
`by_model` en silencio y la respuesta HTTP nunca lo lleva, aunque la función ya lo calcule.
El WebSocket (`astromesh/api/ws.py:123`) publica el diccionario crudo de
`usage_from_trace`, así que ahí el desglose llega sin cambios — no hay que tocar `ws.py`.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_agents_run_usage.py`:

```python
"""El desglose por modelo tiene que sobrevivir al modelo Pydantic de la respuesta."""

from astromesh.api.routes.agents import UsageInfo


def test_usage_info_carries_the_by_model_breakdown():
    usage = UsageInfo(
        tokens_in=180,
        tokens_out=35,
        model="gpt-4o",
        by_model=[
            {
                "provider": "openai",
                "model": "gpt-4o",
                "role": "reasoning",
                "calls": 2,
                "tokens_in": 150,
                "tokens_out": 30,
                "cost": 0.75,
            },
            {
                "provider": "ollama",
                "model": "centinela-4b",
                "role": "classification",
                "calls": 1,
                "tokens_in": 30,
                "tokens_out": 5,
                "cost": 0.0,
            },
        ],
    )

    dumped = usage.model_dump()
    assert len(dumped["by_model"]) == 2
    assert dumped["by_model"][0]["model"] == "gpt-4o"
    assert dumped["by_model"][0]["calls"] == 2
    assert dumped["by_model"][1]["provider"] == "ollama"


def test_usage_info_without_breakdown_still_valid():
    """Compatibilidad hacia atrás: los campos planos solos siguen siendo válidos."""
    usage = UsageInfo(tokens_in=10, tokens_out=4, model="gpt-4o-mini")
    assert usage.by_model == []
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_agents_run_usage.py -v`

Expected: `test_usage_info_carries_the_by_model_breakdown` FALLA con
`KeyError: 'by_model'` al hacer `model_dump()` — Pydantic descartó el campo no declarado.

- [ ] **Step 3: Declarar los modelos**

En `astromesh/api/routes/agents.py`, reemplazar:

```python
class UsageInfo(BaseModel):
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
```

por:

```python
class ModelUsage(BaseModel):
    """Consumo atribuido a un modelo dentro de una corrida.

    Una invocación toca habitualmente varios modelos: por el patrón de
    orquestación, por el enrutamiento por rol, o por fallback entre proveedores.
    """

    provider: str = ""
    model: str = ""
    role: str = "default"
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0


class UsageInfo(BaseModel):
    tokens_in: int = 0
    tokens_out: int = 0
    # Primer modelo visto. Sin valor correcto posible en una corrida multi-modelo;
    # se conserva por compatibilidad. Usar by_model para atribuir consumo.
    model: str = ""
    by_model: list[ModelUsage] = []
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_agents_run_usage.py -v`
Expected: 2 passed.

Run: `uv run pytest tests/ -q`
Expected: sin fallos nuevos respecto de la línea base.

- [ ] **Step 5: Verificar el camino completo a mano**

Run:
```bash
uv run pytest tests/ -k "usage or agents_run" -v
```
Expected: todos los tests de usage y de la respuesta del run pasan.

- [ ] **Step 6: Entrada de changelog**

Ampliar la entrada de `### Added (Core)` creada en la Task 4, agregando al final:

```markdown
  El campo se declara como `usage.by_model` en el modelo de respuesta de
  `POST /v1/agents/{n}/run` (`ModelUsage`), y el WebSocket lo publica en el diccionario de
  `usage` sin cambios adicionales.
```

- [ ] **Step 7: Formato y lint**

Run:
```bash
uv run ruff format astromesh/ tests/
uv run ruff check astromesh/ tests/
```
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git add astromesh/api/routes/agents.py tests/test_agents_run_usage.py CHANGELOG.md
git commit -m "feat(api): exponer usage.by_model en la respuesta del run"
```

---

## Task 6: Release v0.36.0

**Files:**
- Modify: `pyproject.toml` (dos ocurrencias de `version`: `[project]` línea 3 y
  `[tool.commitizen]` línea 90)
- Modify: `astromesh/__init__.py:3` (`__version__`)
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: las entradas de changelog de las Tasks 1-5.
- Produces: el tag `v0.36.0`, que es el que Nexus fija y el que `astromesh-os` puede
  tomar en su `runtime.pin`.

**Contexto para quien implementa:** el repo es un monorepo de paquetes con versiones
independientes. Este release toca **solo el core**: `pyproject.toml`,
`astromesh/__init__.py` y `CHANGELOG.md`. No tocar `astromesh-adk/`, `astromesh-orbit/`,
`astromesh-node/`, `astromesh-cli/` ni `astromesh-forge/`. `## [Unreleased]` ya traía
los arreglos de `parameters` de v0.35.x sin taggear: **todo eso también va a la sección
v0.36.0.**

- [ ] **Step 1: Verificar que la suite completa está en verde**

Run: `uv run pytest -q`
Expected: todos pasan. Anotar el conteo para compararlo con la línea base de 865 passed /
18 skipped más los tests agregados en este plan.

- [ ] **Step 2: Subir la versión en los dos archivos**

En `pyproject.toml`, línea 3 y línea 90: `version = "0.35.1"` → `version = "0.36.0"`.

En `astromesh/__init__.py`, línea 3: `__version__ = "0.35.1"` → `__version__ = "0.36.0"`.

- [ ] **Step 3: Cerrar la sección del changelog**

En `CHANGELOG.md`, reemplazar el encabezado `## [Unreleased]` por
`## [v0.36.0] - 2026-07-21` con todo su contenido debajo, y agregar un
`## [Unreleased]` vacío por encima.

- [ ] **Step 4: Verificar que la versión se reporta bien**

Run: `uv run python -c "import astromesh; print(astromesh.__version__)"`
Expected: `0.36.0`

- [ ] **Step 5: Commit del release**

```bash
git add pyproject.toml astromesh/__init__.py CHANGELOG.md
git commit -m "release: v0.36.0 — RAG sin agentes en disco, alcance de templates, consumo por modelo"
```

- [ ] **Step 6: Tag anotado**

```bash
git tag -a v0.36.0 -m "v0.36.0"
```

**No hacer push.** Ni del commit ni del tag: empujar el tag publica en PyPI. El push queda
a pedido explícito, y después hay que verificar la CI.

---

## Verificación final

- [ ] `uv run pytest -q` en verde
- [ ] `uv run ruff check astromesh/ tests/` limpio
- [ ] `uv run ruff format --check astromesh/ tests/` limpio
- [ ] `git log --oneline v0.35.1..HEAD` muestra los seis commits esperados
- [ ] `CHANGELOG.md` tiene la sección `v0.36.0` con las cuatro entradas de este plan más
      lo que ya traía `[Unreleased]`
- [ ] Ningún archivo de `astromesh-adk/`, `astromesh-orbit/`, `astromesh-node/`,
      `astromesh-cli/` ni `astromesh-forge/` fue modificado

---

## Fuera de alcance, anotado para después

- **Conectar `prompts.templates`.** La Task 2 le da alcance al registro; darle uso es una
  función nueva que necesita su propio diseño (dónde y cómo se invocan los templates).
- **`PromptEngine.render()` recompila la plantilla en cada llamada.** Hace
  `self._env.from_string(template_str).render(...)` en cada corrida, y el prompt de sistema
  se renderiza en cada invocación. En un runtime compartido de alto volumen es camino
  caliente. Candidato a una caché de plantillas compiladas en un release posterior.
- **Costo en `by_model` cuando el proveedor no lo reporta.** `cost` queda en `0.0` si el
  span no lo trae. Atribuir costo a modelos propios (GPU-segundo amortizado) es
  responsabilidad del tarifario de Nexus, no del runtime.
