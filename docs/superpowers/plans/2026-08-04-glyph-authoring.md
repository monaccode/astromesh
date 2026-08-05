# Glyph como lenguaje de autoría (`spec.program`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un agente pueda declarar su programa Glyph en el YAML y ejecutarlo con **cero llamadas al modelo**, en vez de pedirle al modelo que lo reescriba en cada corrida.

**Architecture:** Cinco cambios. `astromesh-glyph` acepta variables predefinidas (para que un programa pueda leer `query` y `context` sin que el compilador las rechace). El core propaga el context del llamador hasta el patrón, que hoy no llega. `GlyphPattern` acepta un programa fijo y salta la generación. `_build_pattern` recibe el catálogo de tools y compila el programa al cargar el agente, de modo que un programa roto sea un fallo de despliegue y no de runtime. Y un agente de ejemplo con la documentación del ciclo de autoría.

**Tech Stack:** Python 3.12+, `uv`, `pytest` (`asyncio_mode = "auto"`), `ruff` (line-length 100, target py312). Sin dependencias nuevas.

## Global Constraints

Aplican a **todas** las tareas.

- **Sin dependencias nuevas**, ni en el core ni en `astromesh-glyph`.
- **`astromesh_glyph` no importa `astromesh`.** La dirección permitida es sólo core → glyph.
- **El import de `astromesh_glyph` va dentro de la función, nunca a nivel de módulo** en `astromesh/runtime/engine.py`: `astromesh/api/main.py` tiene que seguir importando sin extras o la imagen de `astromesh-os` no bootea. Hay un test que lo verifica (`tests/test_glyph_engine.py`).
- **Los demás patrones no cambian de comportamiento.** `react`, `plan_and_execute`, `parallel_fan_out`, `pipeline`, `supervisor` y `swarm` tienen que seguir funcionando igual.
- **La forma del resultado del patrón no cambia**: `{"answer", "steps", "glyph": {...}}`. Un fallo de ejecución devuelve ese mismo dict con `failed: True`, no una excepción — para no romper a los consumidores de la API.
- **Fallar explícito, nunca en silencio.** Nada de fallbacks: si el programa fijo falla, el agente devuelve error. No cae a generar ni a `react`.
- **Regla de changelog (obligatoria)**: los commits `feat:`/`fix:`/`refactor:` que tocan `astromesh/` exigen su entrada en el `CHANGELOG.md` de la raíz bajo `## [Unreleased]`, en el mismo commit. `astromesh-glyph/` lleva su propio `CHANGELOG.md`.
- **`uv.lock` versionado**: ninguna tarea de este plan toca un `pyproject.toml`, así que ningún lock debería moverse. Si alguno se mueve, es un error.
- Lint y formato antes de cada commit. Core: `uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/`. Glyph: lo mismo desde `astromesh-glyph/` sobre `astromesh_glyph/ tests/`.
- Commits convencionales.

---

## Estructura de archivos

| Archivo | Cambio |
|---|---|
| `astromesh-glyph/astromesh_glyph/plan/compiler.py` | **Modificar** — `predefined` en `compile_program` |
| `astromesh-glyph/astromesh_glyph/runtime/executor.py` | **Modificar** — `initial_env` en `execute` |
| `astromesh-glyph/tests/test_compiler.py`, `test_executor.py` | **Modificar** — sus tests |
| `astromesh/runtime/engine.py` | **Modificar** — propagar el context; catálogo a `_build_pattern`; validar en bootstrap |
| `astromesh/orchestration/glyph_pattern.py` | **Modificar** — `program=`, exponer `glyph.program` |
| `tests/test_glyph_pattern.py`, `tests/test_glyph_engine.py` | **Modificar** — sus tests |
| `config/agents/devoluciones-programa.agent.yaml` | **Crear** — el agente de ejemplo |
| `docs/GLYPH_GUIDE.md` | **Modificar** — el ciclo de autoría |
| `CHANGELOG.md`, `astromesh-glyph/CHANGELOG.md` | **Modificar** |

---

## Task 1: Variables predefinidas en `astromesh-glyph`

**Files:**
- Modify: `astromesh-glyph/astromesh_glyph/plan/compiler.py`
- Modify: `astromesh-glyph/astromesh_glyph/runtime/executor.py`
- Test: `astromesh-glyph/tests/test_compiler.py`, `astromesh-glyph/tests/test_executor.py`

**Interfaces:**
- Consumes: `compile_program(program, capabilities)`, `execute(graph, provider, *, node_timeout=None, max_fanout=16)` — ambos ya existen.
- Produces: `compile_program(program, capabilities, predefined=())` donde `predefined` es un iterable de nombres ya ligados al empezar; y `execute(graph, provider, *, node_timeout=None, max_fanout=16, initial_env=None)` donde `initial_env` es el dict de valores iniciales.

**Por qué hace falta:** un programa fijo tiene que poder leer `query` y `context`, y
hoy `compile_program` los rechazaría con «la variable `context` no está definida».
Los dos cambios van juntos: sin el del compilador el programa no compila, y sin el
del executor las variables no tienen valor.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `astromesh-glyph/tests/test_compiler.py`:

```python
def test_a_predefined_name_is_not_undefined():
    """El host puede ligar variables antes de que el programa corra."""
    graph = compile_program(parse("a = search(make=marca)\n"), CAPS, predefined=["marca"])
    assert graph.nodes[0].depends_on == frozenset({"marca"})


def test_a_predefined_name_that_was_not_declared_is_still_rejected():
    with pytest.raises(GlyphCompileError, match="no está definida"):
        compile_program(parse("a = search(make=marca)\n"), CAPS, predefined=["otra"])


def test_a_program_cannot_rebind_a_predefined_name():
    """Ligar `query` de nuevo escondería el valor que el host inyectó."""
    with pytest.raises(GlyphCompileError, match="ya está ligada"):
        compile_program(parse('query = search(make="T")\n'), CAPS, predefined=["query"])


def test_predefined_defaults_to_nothing():
    with pytest.raises(GlyphCompileError, match="no está definida"):
        compile_program(parse("a = search(make=marca)\n"), CAPS)
```

Agregar a `astromesh-glyph/tests/test_executor.py`:

```python
async def test_initial_env_is_visible_to_the_program():
    graph = compile_program(
        parse("a = echo(v=marca)\nreturn a\n"), CAPS, predefined=["marca"]
    )
    result = await execute(graph, Provider(), initial_env={"marca": "Toyota"})
    assert result.value == {"v": "Toyota"}


async def test_initial_env_values_are_wrapped_for_dot_access():
    """Un dict inyectado tiene que soportar `context.campo`, como cualquier registro."""
    graph = compile_program(
        parse("a = echo(v=ctx.orden)\nreturn a\n"), CAPS, predefined=["ctx"]
    )
    result = await execute(graph, Provider(), initial_env={"ctx": {"orden": "A-77"}})
    assert result.value == {"v": "A-77"}


async def test_initial_env_appears_in_the_result_bindings():
    graph = compile_program(parse("a = echo(v=1)\n"), CAPS, predefined=["marca"])
    result = await execute(graph, Provider(), initial_env={"marca": "Toyota"})
    assert result.bindings["marca"] == "Toyota"


async def test_without_initial_env_nothing_extra_is_bound():
    graph = compile_program(parse("a = echo(v=1)\n"), CAPS)
    result = await execute(graph, Provider())
    assert set(result.bindings) == {"a"}
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

```bash
cd astromesh-glyph && uv run pytest tests/ -q -k "predefined or initial_env"
```

Esperado: FAIL — `TypeError: compile_program() got an unexpected keyword argument 'predefined'`.

- [ ] **Step 3: Agregar `predefined` al compilador**

En `astromesh-glyph/astromesh_glyph/plan/compiler.py`, cambiar la firma y la
inicialización de `bound`:

```python
def compile_program(
    program: n.Program,
    capabilities: Sequence[CapabilitySpec],
    predefined: Iterable[str] = (),
) -> PlanGraph:
    """Compila un programa contra un catálogo de capacidades.

    `predefined` son nombres que el host liga antes de que el programa corra —
    `query` y `context` en Astromesh. Sin esto, un programa fijo que lea el
    contexto no compilaría: el compilador los vería como variables sin definir.
    Siguen sujetos a la regla de no reasignar, así que un programa no puede
    pisarlos y esconder el valor inyectado.
    """
    catalog = {cap.name: cap for cap in capabilities}
    bound: set[str] = set(predefined)
    nodes: list[PlanNode] = []
```

Y agregar el import al principio del archivo:

```python
from collections.abc import Iterable, Sequence
```

(la línea actual es `from collections.abc import Sequence`).

- [ ] **Step 4: Agregar `initial_env` al executor**

En `astromesh-glyph/astromesh_glyph/runtime/executor.py`, cambiar la firma y la
inicialización de `env`:

```python
async def execute(
    graph: PlanGraph,
    provider: CapabilityProvider,
    *,
    node_timeout: float | None = None,
    max_fanout: int = DEFAULT_MAX_FANOUT,
    initial_env: dict[str, Any] | None = None,
) -> ExecutionResult:
    # Los valores del host se envuelven igual que lo que devuelve una capacidad,
    # para que `context.campo` funcione sobre un dict inyectado como funciona
    # sobre un resultado.
    env: dict[str, Any] = {k: wrap(v) for k, v in (initial_env or {}).items()}
```

Y agregar `wrap` al import de values, que hoy es `from astromesh_glyph.runtime.values import unwrap`:

```python
from astromesh_glyph.runtime.values import unwrap, wrap
```

- [ ] **Step 5: Correr los tests**

```bash
cd astromesh-glyph && uv run pytest tests/ -q
```

Esperado: PASS. Si `test_without_initial_env_nothing_extra_is_bound` falla, el
default de `initial_env` no está resolviendo a un dict vacío.

- [ ] **Step 6: Actualizar el CHANGELOG de glyph**

En `astromesh-glyph/CHANGELOG.md`, bajo `## [Unreleased]` → `### Added`:

```markdown
- `compile_program(..., predefined=)` y `execute(..., initial_env=)`: el host puede
  ligar variables antes de que el programa corra. Es lo que permite que un programa
  fijo lea el contexto de su invocación sin que el compilador lo rechace.
```

- [ ] **Step 7: Lint, formato y commit**

```bash
cd astromesh-glyph && uv run ruff check astromesh_glyph/ tests/ && uv run ruff format astromesh_glyph/ tests/
cd .. && git add astromesh-glyph/
git commit -m "feat(glyph): variables predefinidas por el host en el compilador y el executor"
```

---

## Task 2: El context del llamador llega al patrón

**Files:**
- Modify: `astromesh/runtime/engine.py:1006`
- Test: `tests/test_glyph_engine.py`

**Interfaces:**
- Consumes: nada de tareas anteriores.
- Produces: la clave reservada `"_caller_context"` dentro del dict `context` que reciben los patrones. Task 3 la lee.

**El estado actual, verificado:** `agent.run(query, session_id, context=None, ...)`
recibe un `context` del llamador. Ese dict se usa para renderizar el prompt
(`engine.py:875`) y para `_provider_override` (`engine.py:895`), pero al patrón se le
pasa `context=memory_context` (`engine.py:1006`) — el contexto de **memoria**, no el
del llamador. Sin este cambio, un programa fijo no tiene de dónde sacar sus
parámetros.

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_glyph_engine.py`:

```python
async def test_the_caller_context_reaches_the_pattern():
    """Hoy no llega: agent.run pasa memory_context al patrón, no el del llamador.

    Sin esto un programa fijo no tiene de dónde sacar sus parámetros, y la
    regresión sería invisible porque ningún patrón existente lo usa.
    """
    from astromesh.orchestration.patterns import OrchestrationPattern

    visto = {}

    class Espia(OrchestrationPattern):
        async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
            visto["context"] = context
            return {"answer": "ok", "steps": []}

    runtime = AgentRuntime()
    await runtime.bootstrap()
    agent = next(iter(runtime._agents.values()))
    agent._pattern = Espia()

    await agent.run("hola", session_id="s1", context={"order_id": "A-77"})

    assert visto["context"]["_caller_context"] == {"order_id": "A-77"}


async def test_a_run_without_caller_context_still_gets_the_key():
    """Vacío, no ausente: así el patrón no tiene que distinguir dos casos."""
    from astromesh.orchestration.patterns import OrchestrationPattern

    visto = {}

    class Espia(OrchestrationPattern):
        async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
            visto["context"] = context
            return {"answer": "ok", "steps": []}

    runtime = AgentRuntime()
    await runtime.bootstrap()
    agent = next(iter(runtime._agents.values()))
    agent._pattern = Espia()

    await agent.run("hola", session_id="s2")

    assert visto["context"]["_caller_context"] == {}


async def test_the_memory_context_survives_the_new_key():
    """La clave nueva se agrega, no reemplaza: _history_messages sigue ahí."""
    from astromesh.orchestration.patterns import OrchestrationPattern

    visto = {}

    class Espia(OrchestrationPattern):
        async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
            visto["context"] = context
            return {"answer": "ok", "steps": []}

    runtime = AgentRuntime()
    await runtime.bootstrap()
    agent = next(iter(runtime._agents.values()))
    agent._pattern = Espia()

    await agent.run("hola", session_id="s3", context={"a": 1})

    assert "_history_messages" in visto["context"]


async def test_react_still_works_with_the_new_context_key():
    """La clave nueva la reciben TODOS los patrones; ninguno puede atragantarse."""
    from astromesh.orchestration.patterns import ReActPattern

    class Respuesta:
        content = "listo"
        tool_calls = None
        usage = {"input_tokens": 5, "output_tokens": 2}

    async def model_fn(messages, tools, role=None):
        return Respuesta()

    result = await ReActPattern().execute(
        query="q",
        context={"_history_messages": [], "_caller_context": {"a": 1}},
        model_fn=model_fn,
        tool_fn=None,
        tools=[],
    )
    assert result["answer"] == "listo"
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

```bash
uv run pytest tests/test_glyph_engine.py -q -k "caller_context or memory_context_survives"
```

Esperado: FAIL — `KeyError: '_caller_context'`.

- [ ] **Step 3: Propagar el context**

En `astromesh/runtime/engine.py`, reemplazar la línea 1006 (`context=memory_context,`)
dentro de la llamada a `self._pattern.execute(...)`:

```python
                # El context del llamador viaja al patrón dentro del dict que ya
                # va, bajo una clave reservada — misma convención que
                # `_history_messages`. Antes se perdía acá: sólo llegaba a
                # renderizar el prompt, así que un patrón no podía leer los
                # parámetros de la invocación.
                context=(
                    {**memory_context, "_caller_context": context or {}}
                    if isinstance(memory_context, dict)
                    else memory_context
                ),
```

- [ ] **Step 4: Correr los tests**

```bash
uv run pytest tests/test_glyph_engine.py -q
```

Esperado: PASS.

- [ ] **Step 5: Correr la suite completa**

```bash
uv run pytest -q
```

Esperado: PASS. Importa correrla entera: el dict de context lo reciben **todos** los
patrones, así que una clave nueva podría romper alguno que itere sus llaves.

- [ ] **Step 6: Actualizar el CHANGELOG y commitear**

En `CHANGELOG.md`, bajo `## [Unreleased]` → `### Fixed`:

```markdown
- El `context` que recibe `agent.run()` ahora llega a los patrones de orquestación,
  bajo la clave reservada `_caller_context`. Antes sólo se usaba para renderizar el
  prompt, así que un patrón no tenía forma de leer los parámetros de la invocación.
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/runtime/engine.py tests/test_glyph_engine.py CHANGELOG.md
git commit -m "fix(runtime): propagar el context del llamador a los patrones de orquestación"
```

---

## Task 3: `GlyphPattern` con programa fijo

**Files:**
- Modify: `astromesh/orchestration/glyph_pattern.py`
- Test: `tests/test_glyph_pattern.py`

**Interfaces:**
- Consumes: `compile_program(..., predefined=)` y `execute(..., initial_env=)` de Task 1; la clave `_caller_context` de Task 2.
- Produces: `GlyphPattern(max_repairs=2, narrate=True, program=None)`; y `glyph.program` en el dict de resultado, con el texto del programa que se ejecutó.

**Las dos variables del programa:** `query` (el texto crudo) y `context` (el dict del
llamador, envuelto para acceso por punto).

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_glyph_pattern.py`:

```python
PROGRAMA_FIJO = 'v = search_parts(make="Toyota")\nreturn v\n'


async def _run_fijo(program, context=None, tool_fn=None, **kwargs):
    async def _default_tool_fn(name, args):
        return [{"sku": "A"}]

    async def _explota(messages, tools, role=None):
        raise AssertionError("el programa fijo no debe llamar al modelo")

    return await GlyphPattern(program=program, narrate=False, **kwargs).execute(
        query="necesito pastillas",
        context={"_caller_context": context or {}},
        model_fn=_explota,
        tool_fn=tool_fn or _default_tool_fn,
        tools=TOOLS,
        max_iterations=6,
    )


async def test_a_fixed_program_never_calls_the_model():
    """Es la afirmación central del diseño: cero llamadas al modelo."""
    result = await _run_fijo(PROGRAMA_FIJO)
    assert result["glyph"]["model_calls"] == 0
    assert result["answer"] == '[{"sku": "A"}]'


async def test_a_fixed_program_still_runs_its_capabilities():
    vistas = []

    async def tool_fn(name, args):
        vistas.append((name, args))
        return [{"sku": "A"}]

    await _run_fijo(PROGRAMA_FIJO, tool_fn=tool_fn)
    assert vistas == [("search_parts", {"make": "Toyota"})]


async def test_the_program_can_read_the_caller_context():
    result = await _run_fijo(
        "v = search_parts(make=context.marca)\nreturn v\n", context={"marca": "Honda"}
    )
    assert result["glyph"]["capability_calls"] == 1


async def test_the_program_can_read_the_query():
    vistas = []

    async def tool_fn(name, args):
        vistas.append(args)
        return [{"sku": "A"}]

    await _run_fijo("v = search_parts(make=query)\nreturn v\n", tool_fn=tool_fn)
    assert vistas == [{"make": "necesito pastillas"}]


async def test_a_failing_capability_reports_failure_without_falling_back():
    async def tool_fn(name, args):
        raise RuntimeError("503 del proveedor")

    result = await _run_fijo(PROGRAMA_FIJO, tool_fn=tool_fn)
    assert result["glyph"]["failed"] is True
    assert result["glyph"]["model_calls"] == 0
    assert "503" in result["answer"]


async def test_the_result_carries_the_program_that_ran():
    result = await _run_fijo(PROGRAMA_FIJO)
    assert result["glyph"]["program"] == PROGRAMA_FIJO


async def test_a_generated_run_also_exposes_its_program():
    """Es lo que cierra el ciclo de autoría: sin esto el programa se descarta."""
    model = ScriptedModel(PROGRAM, "listo")
    result = await _run(model)
    assert 'search_parts(make="Toyota")' in result["glyph"]["program"]


async def test_narration_still_works_with_a_fixed_program():
    """Con `narrate: true` hay UNA llamada —la redacción—, no dos."""

    async def model_fn(messages, tools, role=None):
        return FakeResponse("Encontré una opción.")

    async def tool_fn(name, args):
        return [{"sku": "A"}]

    result = await GlyphPattern(program=PROGRAMA_FIJO, narrate=True).execute(
        query="q",
        context={"_caller_context": {}},
        model_fn=model_fn,
        tool_fn=tool_fn,
        tools=TOOLS,
        max_iterations=6,
    )
    assert result["answer"] == "Encontré una opción."
    assert result["glyph"]["model_calls"] == 1
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

```bash
uv run pytest tests/test_glyph_pattern.py -q -k "fixed or caller_context or the_query or program_that_ran or exposes_its_program"
```

Esperado: FAIL — `TypeError: GlyphPattern.__init__() got an unexpected keyword argument 'program'`.

- [ ] **Step 3: Aceptar el programa en el constructor**

En `astromesh/orchestration/glyph_pattern.py`, reemplazar el `__init__` de
`GlyphPattern`:

```python
    def __init__(self, max_repairs: int = 2, narrate: bool = True, program: str | None = None) -> None:
        self._max_repairs = max_repairs
        # `narrate=False` corta la segunda llamada al modelo y devuelve el
        # resultado del programa como JSON. Un agente encadenado consume
        # `output.data`, no prosa: pedirle al modelo que redacte algo que nadie
        # va a leer es una llamada entera de puro desperdicio.
        self._narrate = narrate
        # Un programa fijo salta la generación entera. Es donde está el 98% del
        # costo del patrón: el modelo reescribiendo el mismo programa en cada
        # corrida. Con esto, una corrida hace cero llamadas al modelo.
        # `max_repairs` se ignora en este modo — no hay nada que reparar, porque
        # un programa que no compila impide que el agente cargue.
        self._program = program
```

- [ ] **Step 4: Saltar la generación y ligar las variables**

En el mismo archivo, dentro de `execute()`, reemplazar el bloque que va desde
`messages = [` hasta el final del `while True:` (o sea, toda la generación y el
ciclo de reparación) por una bifurcación. El código nuevo:

```python
    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        capabilities = PatternCapabilities(tools=tools, tool_fn=tool_fn, model_fn=model_fn)
        catalog = capabilities.list_capabilities()
        history = context.get("_history_messages", []) if isinstance(context, dict) else []
        caller_context = context.get("_caller_context", {}) if isinstance(context, dict) else {}
        # Las dos variables que ve un programa. Van siempre, aunque el programa no
        # las use: el compilador las acepta como predefinidas y no cuesta nada.
        env = {"query": query, "context": caller_context}

        steps: list[AgentStep] = []
        model_calls = 0
        repairs = 0
        result = None
        failure = None
        source = self._program or ""

        if self._program is not None:
            try:
                graph = compile_program(parse(source), catalog, predefined=env)
                result = await execute(graph, capabilities, initial_env=env)
            except (GlyphSyntaxError, GlyphCompileError, GlyphExecutionError) as exc:
                failure = exc
        else:
            block = build_system_block(catalog)
            messages = [
                *list(history),
                {"role": "user", "content": block},
                {"role": "user", "content": query},
            ]
            budget = max(0, min(self._max_repairs, max_iterations - 1))

            while True:
                response = await model_fn(messages, [], role="reasoner")
                model_calls += 1
                source = extract_program(response.content or "")

                try:
                    graph = compile_program(parse(source), catalog, predefined=env)
                    result = await execute(graph, capabilities, initial_env=env)
                    break
                except (GlyphSyntaxError, GlyphCompileError, GlyphExecutionError) as exc:
                    failure = exc
                    if repairs >= budget:
                        break
                    repairs += 1
                    logger.info(
                        "glyph: reparación %d/%d tras %s", repairs, budget, type(exc).__name__
                    )
                    messages = [
                        *messages,
                        {"role": "assistant", "content": response.content},
                        {"role": "user", "content": _repair_prompt(exc)},
                    ]
```

Nota: `predefined=env` funciona porque el compilador sólo necesita los **nombres**, y
un dict itera sus claves.

- [ ] **Step 5: Exponer el programa en los dos caminos de salida**

En el mismo archivo, agregar `"program": source` a los dos dicts `"glyph"` que
devuelve `execute()`. El del fallo:

```python
                "glyph": {
                    "model_calls": model_calls,
                    "capability_calls": 0,
                    "semantic_calls": capabilities.semantic_calls,
                    "repairs": repairs,
                    "failed": True,
                    "program": source,
                },
```

Y el del éxito (hay dos: el de `narrate: false` y el de la narración) — los tres
llevan la misma clave:

```python
                "program": source,
```

- [ ] **Step 6: Correr los tests**

```bash
uv run pytest tests/test_glyph_pattern.py -q
```

Esperado: PASS.

- [ ] **Step 7: Correr la suite completa**

```bash
uv run pytest -q
```

Esperado: PASS.

- [ ] **Step 8: Actualizar el CHANGELOG y commitear**

En `CHANGELOG.md`, bajo `## [Unreleased]` → `### Added (Backend)`:

```markdown
- `GlyphPattern(program=...)`: un agente puede traer su programa Glyph ya escrito y
  ejecutarlo con **cero llamadas al modelo**. El 98% del costo del patrón era el
  modelo reescribiendo el mismo programa en cada corrida. El programa lee `query` y
  `context` (el del llamador) como variables predefinidas.
- El resultado del patrón expone `glyph.program` con el texto del programa que
  corrió, para poder capturar el que el modelo generó y fijarlo en el YAML.
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/orchestration/glyph_pattern.py tests/test_glyph_pattern.py CHANGELOG.md
git commit -m "feat(glyph): ejecutar un programa fijo sin llamar al modelo"
```

---

## Task 4: Validación en el bootstrap

**Files:**
- Modify: `astromesh/runtime/engine.py:603` y `:625`
- Test: `tests/test_glyph_engine.py`

**Interfaces:**
- Consumes: `GlyphPattern(program=...)` de Task 3.
- Produces: `_build_pattern(self, spec: dict, tool_schemas: list[dict] | None = None)`. Un `spec.program` que no compila impide que el agente cargue.

**Contexto:** `_build_pattern(spec)` se define en `engine.py:625` y se invoca en
`engine.py:603`. El `ToolRegistry` del agente ya está construido para ese momento
(`engine.py:482`, variable local `tools`), así que el catálogo está disponible sin
mover nada de orden.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_glyph_engine.py`:

```python
_TOOLS_YAML = [
    {
        "type": "function",
        "function": {
            "name": "buscar",
            "description": "Busca algo",
            "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
        },
    }
]


def test_a_valid_program_reaches_the_pattern():
    runtime = AgentRuntime.__new__(AgentRuntime)
    pattern = runtime._build_pattern(
        {"orchestration": {"pattern": "glyph"}, "program": 'x = buscar(q="a")\nreturn x\n'},
        _TOOLS_YAML,
    )
    assert pattern._program == 'x = buscar(q="a")\nreturn x\n'


def test_a_program_that_does_not_compile_stops_the_agent_from_loading():
    """Un programa roto es un error de despliegue, no de la primera consulta."""
    from astromesh_glyph import GlyphCompileError

    runtime = AgentRuntime.__new__(AgentRuntime)
    with pytest.raises(GlyphCompileError, match="no existe"):
        runtime._build_pattern(
            {"orchestration": {"pattern": "glyph"}, "program": "x = inventada()\n"},
            _TOOLS_YAML,
        )


def test_a_program_with_a_syntax_error_stops_the_agent_from_loading():
    from astromesh_glyph import GlyphSyntaxError

    runtime = AgentRuntime.__new__(AgentRuntime)
    with pytest.raises(GlyphSyntaxError):
        runtime._build_pattern(
            {"orchestration": {"pattern": "glyph"}, "program": "x = = 1\n"}, _TOOLS_YAML
        )


def test_the_program_may_read_query_and_context():
    """Son predefinidas: un programa que las use tiene que compilar."""
    runtime = AgentRuntime.__new__(AgentRuntime)
    pattern = runtime._build_pattern(
        {"orchestration": {"pattern": "glyph"}, "program": "x = buscar(q=context.id)\nreturn x\n"},
        _TOOLS_YAML,
    )
    assert pattern._program is not None


def test_a_program_declared_with_another_pattern_stops_the_agent_from_loading():
    """Es un error de configuración: el programa no se ejecutaría nunca."""
    runtime = AgentRuntime.__new__(AgentRuntime)
    with pytest.raises(ValueError, match="pattern: glyph"):
        runtime._build_pattern(
            {"orchestration": {"pattern": "react"}, "program": "x = buscar(q=1)\n"}, _TOOLS_YAML
        )


def test_an_agent_without_a_program_still_builds():
    from astromesh.orchestration.glyph_pattern import GlyphPattern

    runtime = AgentRuntime.__new__(AgentRuntime)
    pattern = runtime._build_pattern({"orchestration": {"pattern": "glyph"}}, _TOOLS_YAML)
    assert isinstance(pattern, GlyphPattern)
    assert pattern._program is None
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

```bash
uv run pytest tests/test_glyph_engine.py -q -k "program"
```

Esperado: FAIL — `TypeError: _build_pattern() takes 2 positional arguments but 3 were given`.

- [ ] **Step 3: Cambiar la firma y validar**

En `astromesh/runtime/engine.py`, reemplazar la cabecera y el bloque `glyph` de
`_build_pattern`:

```python
    def _build_pattern(self, spec: dict, tool_schemas: list[dict] | None = None):
        """Instancia el patrón de orquestación declarado en el YAML.

        `glyph` se importa acá adentro y no arriba: `astromesh_glyph` es un extra
        opcional, y `astromesh/api/main.py` tiene que seguir importando sin extras
        o la imagen de astromesh-os no bootea.

        Cuando el spec trae `program`, se compila acá contra el catálogo de tools
        del agente. Un programa roto se convierte así en un fallo de despliegue con
        línea y mensaje, en vez de un error en la cara del primer cliente.
        """
        pattern_map = {
            "react": ReActPattern,
            "plan_and_execute": PlanAndExecutePattern,
            "parallel_fan_out": ParallelFanOutPattern,
            "pipeline": PipelinePattern,
            "supervisor": SupervisorPattern,
            "swarm": SwarmPattern,
        }
        pattern_name = spec.get("orchestration", {}).get("pattern", "react")
        program = spec.get("program")

        if program is not None and pattern_name != "glyph":
            raise ValueError(
                f"el agente declara `program` pero su pattern es {pattern_name!r}: "
                "un programa Glyph sólo lo ejecuta `pattern: glyph`"
            )

        if pattern_name == "glyph":
            try:
                orchestration = spec.get("orchestration", {})
                glyph_pattern = _import_glyph_pattern(pattern_name)
            except ImportError:
                logger.warning(
                    "el agente pide pattern=glyph pero el extra no está instalado "
                    "(pip install 'astromesh[glyph]'); se usa react",
                )
                return ReActPattern()

            if program is not None:
                # Compila para que un programa roto no cargue. La excepción sube:
                # es un error de configuración y tiene que ser ruidoso.
                _compile_glyph_program(program, tool_schemas or [])

            # `narrate: false` ahorra la segunda llamada al modelo devolviendo
            # el resultado del programa como JSON. Un agente que alimenta a
            # otro eslabón consume `output.data`, no prosa.
            return glyph_pattern(
                max_repairs=int(orchestration.get("max_repairs", 2)),
                narrate=bool(orchestration.get("narrate", True)),
                program=program,
            )

        return pattern_map.get(pattern_name, ReActPattern)()
```

Nótese que el `try/except ImportError` ahora envuelve **sólo** el import: antes
envolvía también la construcción, así que un `ImportError` que naciera adentro del
patrón se habría confundido con el extra faltante.

- [ ] **Step 4: Agregar el helper de compilación**

Al final de `astromesh/runtime/engine.py`, junto a `_import_glyph_pattern`:

```python
def _compile_glyph_program(program: str, tool_schemas: list[dict]) -> None:
    """Compila un programa del YAML contra el catálogo del agente.

    Import diferido por la misma razón que `_import_glyph_pattern`: el extra es
    opcional. Deja subir `GlyphSyntaxError` / `GlyphCompileError` — un programa
    roto tiene que impedir que el agente cargue.
    """
    from astromesh_glyph import compile_program, parse

    from astromesh.orchestration.glyph_pattern import PatternCapabilities

    catalog = PatternCapabilities(
        tools=tool_schemas, tool_fn=None, model_fn=None
    ).list_capabilities()
    compile_program(parse(program), catalog, predefined=("query", "context"))
```

- [ ] **Step 5: Pasar el catálogo en la invocación**

En `astromesh/runtime/engine.py:603`, reemplazar `pattern = self._build_pattern(spec)`:

```python
        pattern = self._build_pattern(
            spec, tools.get_tool_schemas(spec.get("permissions", {}).get("allowed_actions"))
        )
```

- [ ] **Step 6: Correr los tests**

```bash
uv run pytest tests/test_glyph_engine.py -q
```

Esperado: PASS.

- [ ] **Step 7: Correr la suite completa**

```bash
uv run pytest -q
```

Esperado: PASS. `_build_pattern` está en el camino que arma **todos** los agentes:
si algo se rompe acá, se rompe el bootstrap entero.

- [ ] **Step 8: Actualizar el CHANGELOG y commitear**

En `CHANGELOG.md`, bajo `## [Unreleased]` → `### Added (Backend)`:

```markdown
- `spec.program` en el YAML de un agente: el programa Glyph se compila contra el
  catálogo de tools **al cargar el agente**, así que un programa roto es un fallo de
  despliegue con línea y mensaje y no un error en la primera consulta. Declararlo con
  un `pattern` distinto de `glyph` también impide cargar.
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/runtime/engine.py tests/test_glyph_engine.py CHANGELOG.md
git commit -m "feat(glyph): validar spec.program al cargar el agente"
```

---

## Task 5: Agente de ejemplo y el ciclo de autoría

**Files:**
- Create: `config/agents/devoluciones-programa.agent.yaml`
- Modify: `docs/GLYPH_GUIDE.md`
- Test: `tests/test_glyph_engine.py`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: nada que otras tareas usen.

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_glyph_engine.py`:

```python
def test_the_example_agent_loads_and_carries_its_program():
    """El ejemplo tiene que compilar de verdad, no ser prosa en un YAML."""
    import yaml

    from astromesh.orchestration.glyph_pattern import GlyphPattern

    spec = yaml.safe_load(
        pathlib.Path("config/agents/devoluciones-programa.agent.yaml").read_text()
    )["spec"]

    schemas = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": {"type": "object", "properties": t.get("parameters", {})},
            },
        }
        for t in spec["tools"]
    ]

    runtime = AgentRuntime.__new__(AgentRuntime)
    pattern = runtime._build_pattern(spec, schemas)
    assert isinstance(pattern, GlyphPattern)
    assert pattern._program is not None
    assert pattern._narrate is False
```

Y agregar `import pathlib` al principio de `tests/test_glyph_engine.py` si no está.

- [ ] **Step 2: Correr el test para verificar que falla**

```bash
uv run pytest tests/test_glyph_engine.py -q -k example_agent
```

Esperado: FAIL — `FileNotFoundError`.

- [ ] **Step 3: Crear el agente de ejemplo**

`config/agents/devoluciones-programa.agent.yaml`:

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: devoluciones-programa
  version: "1.0.0"
  namespace: support

spec:
  identity:
    display_name: "Devoluciones (programa fijo)"
    description: >
      Resuelve una solicitud de devolución con un programa Glyph escrito de
      antemano. No consulta al modelo: cero llamadas por corrida.

  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"
      endpoint: "http://localhost:11434"

  prompts:
    system: |
      Agente de devoluciones. No se usa: el programa corre sin modelo.

  orchestration:
    pattern: glyph
    # Sin narración: el resultado se devuelve como JSON para que lo consuma otro
    # eslabón. Con `narrate: true` habría una llamada al modelo para redactar.
    narrate: false

  # El programa lo escribió el modelo una vez (ver el ciclo de autoría en
  # docs/GLYPH_GUIDE.md) y se fijó acá después de revisarlo. `context` son los
  # parámetros de la invocación; se parametrizó lo que la consulta de autoría
  # había dejado hardcodeado.
  program: |
    orden = find_order(order_id=context.order_id)
    politica = refund_policy()
    if orden.days_since < politica.window_days:
        ticket = open_ticket(order_id=context.order_id)
    return {orden, politica, ticket}

  tools:
    - name: find_order
      type: client
      description: Busca una orden por su identificador
      parameters:
        order_id:
          type: string
          description: Identificador de la orden
    - name: refund_policy
      type: client
      description: Devuelve la política de devoluciones vigente
      parameters: {}
    - name: open_ticket
      type: client
      description: Abre un ticket de devolución
      parameters:
        order_id:
          type: string
          description: Identificador de la orden
```

- [ ] **Step 4: Correr el test**

```bash
uv run pytest tests/test_glyph_engine.py -q -k example_agent
```

Esperado: PASS. Si falla con `GlyphCompileError`, el programa del YAML no cuadra con
las tools declaradas — arreglar el programa, no el test.

- [ ] **Step 5: Documentar el ciclo de autoría**

En `docs/GLYPH_GUIDE.md`, insertar una sección nueva justo después de
`## 3 · Cómo se configura`:

````markdown
---

## 3b · Programa fijo: el modelo escribe una vez

El 98% de lo que cuesta Glyph es el modelo escribiendo el programa, y lo reescribe
idéntico en cada corrida. Si la tarea del agente es estable, escribilo una vez y
fijalo:

```yaml
spec:
  orchestration:
    pattern: glyph
    narrate: false
  program: |
    orden = find_order(order_id=context.order_id)
    politica = refund_policy()
    if orden.days_since < politica.window_days:
        ticket = open_ticket(order_id=context.order_id)
    return {orden, politica, ticket}
```

Con `narrate: false` y sin `ask()`, **una corrida hace cero llamadas al modelo**:

| | costo/corrida | vs ReAct |
|---|---:|---:|
| ReAct | 0,00623 USD | — |
| Glyph generando el programa | 0,03226 USD | +418% |
| **`spec.program`** | **0,00000 USD** | **−100%** |

### Las dos variables del programa

| variable | qué es |
|---|---|
| `query` | el texto crudo de la consulta |
| `context` | el dict que recibió `agent.run(...)`, con acceso por punto |

Para sacar campos de texto libre está `ask()`, que cuesta ~30 tokens de salida
contra los ~8.000 de escribir el programa:

```glyph
id = ask("Devolvé sólo el número de orden, sin nada más.", context=query)
orden = find_order(order_id=id)
```

### El ciclo de autoría

1. Corré el agente **una vez** sin `program`, con una consulta representativa.
2. El resultado trae `glyph.program`: el texto que el modelo escribió.
3. Revisalo y **parametrizá lo que quedó hardcodeado** de esa consulta —
   típicamente los identificadores, que hay que cambiar por `context.<campo>`.
4. Pegalo en `spec.program`. A partir de ahí el agente corre sin modelo.

El modelo es el autor, vos el revisor, el runtime el ejecutor.

### Qué falla y cuándo

| cuándo | qué pasa |
|---|---|
| El programa no compila | **El agente no carga.** Error de despliegue con línea y mensaje. |
| Una capacidad falla en ejecución | El agente devuelve error con el estado parcial. **No** cae a generar ni a `react`. |
| `spec.program` con otro `pattern` | El agente no carga. |

Fallar explícito es deliberado: caer a generar traería el costo de vuelta cuando
menos se lo espera, y caer a `react` mezclaría dos modos que difieren 400x en costo
bajo un mismo agente.

### Cuándo NO usarlo

Si cada consulta necesita un plan distinto, este modo no aplica — el programa fijo
es un contrato, no una sugerencia. Un agente con programa fijo **deja de ser
conversacional**, y eso es consecuencia del diseño, no un defecto.
````

- [ ] **Step 6: Correr la suite y commitear**

```bash
uv run pytest -q && uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add config/agents/devoluciones-programa.agent.yaml docs/GLYPH_GUIDE.md tests/test_glyph_engine.py
git commit -m "docs(glyph): agente de ejemplo con programa fijo y ciclo de autoría"
```

---

## Cierre

Al terminar, verificar a mano lo que ningún test cubre: que el ejemplo corre de
punta a punta contra tools reales. Los tests comprueban que compila y que el patrón
se arma; que las tools `client` respondan es cosa del despliegue.

Y anotar en el spec —sección Riesgos— cualquier caso real donde el programa fijo
haya resultado insuficiente. Es el supuesto sin verificar del diseño, y sólo se
aprende usándolo.
