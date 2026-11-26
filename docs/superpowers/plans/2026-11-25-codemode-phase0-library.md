# astromesh-codemode — Fase 0 (librería) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publicar `astromesh-codemode` 0.1.0: envuelve tools (funciones Python, servidores MCP) en dos tools `search`/`run` que ejecutan el programa del modelo en un sandbox Monty, con adaptadores para 8 frameworks, un proxy MCP, y dos evals (costo y trampas) — con el nivel 2 del eval de costo publicado **antes** de PyPI.

**Architecture:** `ToolSpec` neutral → `catalog` (stubs Python + índice BM25) → `CodeMode` arma `search` y `run`; `run` ejecuta en `pydantic_monty.AsyncMonty` (pool de workers en subproceso, una sesión limpia por `run`) con las tools como funciones externas async, contando llamadas y capturando un `Trace`. Adaptadores y proxy MCP sólo traducen `CodeMode` a la forma de cada framework.

**Tech Stack:** Python ≥3.11, `pydantic-monty==1.7.*`, `jsonschema`, `mcp` (extra), `tiktoken` + `litellm` (extra `eval`), pytest + pytest-asyncio, uv, hatchling.

**Spec:** `docs/superpowers/specs/2026-11-25-codemode-design.md` (repo `astromesh`). Logo: `docs/superpowers/specs/codemode-assets/`.

**Plan de la fase 1 (core):** se escribe aparte después de la Task 11; no empieza antes de que el nivel 2 esté publicado.

## Global Constraints

- Repo nuevo `monaccode/astromesh-codemode` (público), en `D:\monaccode\astromesh-codemode`, rama `main` + `develop` como las hermanas; Apache-2.0.
- Python ≥3.11 (`requires-python = ">=3.11"`); dependencias base: `pydantic-monty>=1.7,<1.8`, `jsonschema>=4.20`. Nada más en base.
- Paquete `astromesh_codemode`; versión `0.1.0` en `pyproject.toml` y `astromesh_codemode/__init__.py` (`__version__`), siempre iguales.
- Límites por defecto (spec 3.3): `timeout_s=30`, `max_memory=64 * 1024 * 1024`, `max_calls=50`, `max_output_bytes=16384`.
- Sin estado entre `run`s: cada `run` usa una sesión nueva (`pool.checkout(...)`).
- v0.1 es de lectura: tools `writes=True` no entran al sandbox salvo `allow_writes=True`; en fuentes MCP toda tool es escritura salvo `readOnlyHint: true` o listada como lectura.
- Errores al modelo: texto `"<Tipo> (línea N): <mensaje>"` (sin línea si Monty no la da); nunca un traceback del host.
- README + README.es; el README no dice "conviene a partir de…" hasta que exista la tabla del nivel 2 (Task 10).
- Ruff (line-length 100) y `ruff format --check` en CI, como el core.

## Review Focus

1. Dos tools cuyos nombres colisionan al volverse identificadores Python (`get-user` y `get_user`): `CodeMode(...)` levanta `ValueError` nombrando ambas; nunca una pisa a la otra. → test en Task 2.
2. Una tool o el programa devuelven algo no serializable a JSON (`bytes`, `datetime`, objetos): `run` devuelve texto legible (`repr`/`isoformat`), no una excepción del host. → test en Task 4.
3. Un programa que sólo imprime y no devuelve valor: la salida trae lo impreso y `result: None`, no un string vacío. → test en Task 4.
4. Dos `run` concurrentes sobre el mismo `CodeMode` (frameworks que paralelizan tool calls): contadores de llamadas y traces separados, sin compartir sesión. → test en Task 4.
5. `search` con `limit` absurdo (10000) o query vacía: `limit` se recorta a 25; query vacía devuelve las primeras tools por orden de registro, no error. → test en Task 3.

---

### Task 1: Repo, empaquetado y `ToolSpec`

**Files:**
- Create: `pyproject.toml`, `LICENSE` (Apache-2.0, copiar de `astromesh-a2a`), `CHANGELOG.md` (`## [Unreleased]`), `.gitignore`, `assets/{logo-mark.svg,logo.png,icon.png}` (copiar de `astromesh/docs/superpowers/specs/codemode-assets/`), `astromesh_codemode/__init__.py`, `astromesh_codemode/spec.py`, `.github/workflows/ci.yml` (calcar `astromesh-a2a`: uv sync --locked, ruff check, ruff format --check, pytest)
- Test: `tests/test_spec.py`

**Interfaces:**
- Produces: `ToolSpec` (dataclass frozen): `name: str`, `description: str`, `input_schema: dict`, `handler: Callable[..., Awaitable[Any]]`, `output_schema: dict | None = None`, `writes: bool = False`. `__version__ = "0.1.0"`.
- Produces: `ToolError(Exception)` en `spec.py`.

- [ ] **Step 1:** `git init` en `D:\monaccode\astromesh-codemode`, `pyproject.toml` (hatchling; extras vacíos por ahora: `mcp`, `otel`, `eval`, `all`, uno por framework se agrega en Task 6/7/9), `uv lock`.
- [ ] **Step 2: Test** `test_toolspec_defaults`: `ToolSpec("a","d",{"type":"object"},handler)` tiene `writes is False` y `output_schema is None`; `test_version`: `astromesh_codemode.__version__ == "0.1.0"`.
- [ ] **Step 3:** Run `uv run pytest tests/test_spec.py -v` → FAIL (módulo no existe).
- [ ] **Step 4:** Implementar `spec.py` y exportar `ToolSpec`, `ToolError`, `__version__` desde `__init__.py`.
- [ ] **Step 5:** Run → PASS; `uv run ruff check . && uv run ruff format --check .` → limpio.
- [ ] **Step 6: Commit** `chore: scaffold de astromesh-codemode con ToolSpec`.

### Task 2: Stubs Python desde JSON Schema

**Files:**
- Create: `astromesh_codemode/stubs.py`
- Test: `tests/test_stubs.py`

**Interfaces:**
- Consumes: `ToolSpec`.
- Produces: `py_name(tool_name: str) -> str` (regex `\W`→`_`, prefijo `_` si empieza con dígito); `annotation(schema: dict) -> str`; `render_stub(spec: ToolSpec) -> str`; `index_by_py_name(specs: list[ToolSpec]) -> dict[str, ToolSpec]` (levanta `ValueError` en colisión).

- [ ] **Step 1: Tests**
  - `test_annotation_basic`: `string→"str"`, `integer→"int"`, `number→"float"`, `boolean→"bool"`, `array` de `string`→`"list[str]"`, `object`→`"dict"`, `["string","null"]`→`"str | None"`, `enum ["a","b"]`→`'Literal["a", "b"]'`, sin `type`→`"Any"`.
  - `test_render_stub`: tool `crm-get contact` con `required: ["id"]`, props `id: integer`, `fields: array<string>` → contiene `async def crm_get_contact(id: int, fields: list[str] | None = None) -> Any:` y la descripción como docstring de una línea.
  - `test_collision` *(Review Focus 1)*: `index_by_py_name([get-user, get_user])` → `ValueError` cuyo mensaje contiene `"get-user"` y `"get_user"`.
- [ ] **Step 2:** Run `uv run pytest tests/test_stubs.py -v` → FAIL.
- [ ] **Step 3:** Implementar. Requeridos primero, opcionales con `= None`; retorno `annotation(output_schema)` si existe, si no `Any`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5: Commit** `feat: stubs Python tipados desde JSON Schema`.

### Task 3: Índice de búsqueda (BM25)

**Files:**
- Create: `astromesh_codemode/search.py`
- Test: `tests/test_search.py`

**Interfaces:**
- Produces: `class Index: __init__(self, specs: list[ToolSpec])`; `search(self, query: str, limit: int = 8) -> list[ToolSpec]`. Constante `MAX_LIMIT = 25`.

- [ ] **Step 1: Tests**
  - `test_ranks_by_name_and_description`: catálogo de 64 tools sintéticas (helper `tests/fixtures.py::synthetic_catalog(n)` que también usará el eval); `search("invoice total")` pone `billing_get_invoice` primero.
  - `test_param_names_count`: una tool sin la palabra en nombre/descr pero con parámetro `customer_email` aparece para `"customer email"`.
  - `test_limits` *(Review Focus 5)*: `search("x", limit=10000)` devuelve ≤25; `search("", 5)` devuelve las primeras 5 en orden de registro.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implementar BM25 a mano (k1=1.5, b=0.75) sobre tokens en minúscula de nombre (partido por `_`, `-`, camelCase), descripción y nombres de parámetros; empate por orden de registro.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5: Commit** `feat: búsqueda léxica BM25 sobre el catálogo`.

### Task 4: Sandbox, `CodeMode` y `Trace`

**Files:**
- Create: `astromesh_codemode/limits.py`, `astromesh_codemode/sandbox.py`, `astromesh_codemode/trace.py`, `astromesh_codemode/codemode.py`
- Modify: `astromesh_codemode/__init__.py` (exportar `CodeMode`, `Limits`, `Trace`)
- Test: `tests/test_sandbox.py`, `tests/test_codemode.py`

**Interfaces:**
- Consumes: `ToolSpec`, `ToolError`, `index_by_py_name`, `render_stub`, `Index`.
- Produces:
  - `Limits` (dataclass frozen): `timeout_s: float = 30`, `max_memory: int = 64*1024*1024`, `max_calls: int = 50`, `max_output_bytes: int = 16384`.
  - `CallRecord(tool: str, args_preview: str, ms: float, bytes: int, error: str | None)`; `Trace(code: str, calls: list[CallRecord], result_preview: str, error: str | None, limit_hit: str | None, ms: float)` con `to_dict() -> dict`.
  - `class CodeMode`: `__init__(self, tools: list[ToolSpec], *, name: str = "codemode", limits: Limits = Limits(), allow_writes: bool = False)`; `async search(self, query: str, limit: int = 8) -> str`; `async run(self, code: str) -> str`; `tool_definitions(self) -> list[NeutralTool]`; `last_trace: Trace | None`; `async aclose(self)`; usable como `async with`.
  - `NeutralTool` (dataclass): `name: str` (`f"{name}_search"` / `f"{name}_run"`), `description: str`, `parameters: dict` (JSON Schema), `handler: Callable[..., Awaitable[str]]`.
  - `trace.emit_otel(trace: Trace) -> None` (extra `otel = ["opentelemetry-api>=1.27"]`): un span `codemode.run` con un span hijo por `CallRecord`; sin el extra es no-op.

- [ ] **Step 1: Tests de `run`** (handlers de prueba en `tests/fixtures.py`: `get_rows(n)` devuelve n dicts, `boom()` levanta `ToolError("crm caído")`, `stamp()` devuelve `datetime`, `save(x)` con `writes=True`):
  - `test_run_filters_large_data`: `rows = await get_rows(n=500)` + comprehension → la salida contiene los 2 ids esperados y **no** contiene `"id": 3`; `last_trace.calls` tiene 1 registro de `get_rows`.
  - `test_tool_error_is_catchable`: `try/except Exception as e: str(e)` → salida contiene `"crm caído"`.
  - `test_args_validated_against_schema`: `await get_rows(n="x")` → salida empieza con un tipo de error y contiene `"get_rows"`; el handler no se llamó.
  - `test_max_calls`: `Limits(max_calls=3)` y un bucle de 5 llamadas → error que contiene `"max_calls"`; `last_trace.limit_hit == "max_calls"`.
  - `test_output_truncated`: devolver `"x" * 50_000` con default → salida ≤ 16384 bytes + aviso `"[truncated"`.
  - `test_timeout`: `Limits(timeout_s=1)` con `while True: pass` → error con `"TimeoutError"`; `limit_hit == "timeout"`.
  - `test_non_json_values` *(Review Focus 2)*: `return await stamp()` → la salida contiene el ISO de la fecha.
  - `test_print_only` *(Review Focus 3)*: `print("hola")` sin retorno → salida contiene `"hola"` y `"result: None"`.
  - `test_concurrent_runs_isolated` *(Review Focus 4)*: `asyncio.gather` de dos `run` con 2 y 3 llamadas → cada salida/trace con su propio conteo (usar `run_with_trace` interno o comparar las salidas).
  - `test_writes_excluded`: `save` no aparece en `search` y `await save(x=1)` → `NameError`; con `allow_writes=True` sí corre.
  - `test_no_state_between_runs`: `x = 1` en un run; `x` en el siguiente → `NameError`.
  - `test_emit_otel` (`importorskip("opentelemetry")`, `InMemorySpanExporter`): un `run` con 2 llamadas emite `codemode.run` y 2 hijos con el nombre de la tool.
- [ ] **Step 2: Tests de `search` y definiciones**: `search("rows")` devuelve texto con `async def get_rows(` y su descripción; `tool_definitions()` devuelve 2 `NeutralTool` llamadas `codemode_search` y `codemode_run`, cuyos `parameters` requieren `query` y `code` respectivamente; las descripciones dicen que hay que buscar antes de ejecutar y que las tools se llaman con `await` y argumentos por nombre.
- [ ] **Step 3:** Run `uv run pytest tests/test_sandbox.py tests/test_codemode.py -v` → FAIL.
- [ ] **Step 4:** Implementar. Un `AsyncMonty` por `CodeMode` (lazy, cerrado en `aclose`); por `run`: `pool.checkout(limits={"max_feed_duration_secs": timeout_s, "max_memory": max_memory})` y `feed_run(code, external_lookup=…, print_callback=CollectString())`. Cada tool expuesta como closure async que: suma al contador del run (levanta `ToolError("max_calls …")` al pasarse), valida kwargs con `jsonschema`, llama `handler(**kwargs)`, registra `CallRecord`. Serialización de salida: `json.dumps(default=_fallback)` (`isoformat` para fechas, `repr` para lo demás). Errores de Monty (`MontySyntaxError`, `MontyTypingError`, `MontyRuntimeError`) → `"<Tipo> (línea N): <mensaje>"`.
- [ ] **Step 5:** Run → PASS.
- [ ] **Step 6: Commit** `feat: CodeMode con search/run sobre Monty, límites y trace`.

### Task 5: Fuentes — funciones Python y servidores MCP

**Files:**
- Create: `astromesh_codemode/sources/__init__.py`, `sources/functions.py`, `sources/mcp.py`
- Modify: `pyproject.toml` (extra `mcp = ["mcp>=1.28"]`)
- Test: `tests/test_sources.py`

**Interfaces:**
- Produces: `from_function(fn: Callable, *, name: str | None = None, description: str | None = None, writes: bool = False) -> ToolSpec` (schema desde type hints y docstring; sync se envuelve en `asyncio.to_thread`); `async from_mcp(session: mcp.ClientSession, *, prefix: str = "", read_only: set[str] = frozenset()) -> list[ToolSpec]`.

- [ ] **Step 1: Tests**
  - `test_from_function_schema`: `def f(a: int, b: str = "x") -> list[str]` → `input_schema` requiere `a`, `b` opcional; `output_schema` es array de string; un `f` sync corre vía el handler async.
  - `test_from_mcp_readonly_rule` (servidor en memoria con `mcp.shared.memory.create_connected_server_and_client_session` y FastMCP con 3 tools: una con `readOnlyHint=True`, una sin anotación, una listada en `read_only`): las dos primeras resultan `writes=False/True` según la regla (anotación → lectura, sin anotación → escritura) y la listada → lectura.
  - `test_from_mcp_call`: la tool de lectura, envuelta en `CodeMode`, devuelve su resultado (contenido de texto/estructurado del `CallToolResult`) dentro del programa.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementar. **Step 4:** Run → PASS.
- [ ] **Step 5: Commit** `feat: fuentes desde funciones Python y servidores MCP`.

### Task 6: Adaptadores de framework

**Files:**
- Create: `astromesh_codemode/adapters/{__init__,langchain,pydantic_ai,openai_agents,adk,crewai,llamaindex,smolagents,agent_framework}.py`
- Modify: `pyproject.toml` (extras con las mismas cotas que `astromesh-a2a`: `langchain-core>=1.6`, `pydantic-ai-slim>=2.55`, `openai-agents>=0.20`, `google-adk>=1.14`, `crewai>=1.15`, `llama-index-core>=0.14`, `smolagents>=1.26`, `agent-framework>=1.19`)
- Test: `tests/adapters/test_<framework>.py` (uno por adaptador, `pytest.importorskip`)

**Interfaces:**
- Consumes: `CodeMode.tool_definitions() -> list[NeutralTool]`.
- Produces: en cada módulo `as_tools(cm: CodeMode) -> list[<tool nativa del framework>]`.

- [ ] **Step 1: Test por adaptador** (mismo patrón): construye `CodeMode([get_rows])`, `as_tools(cm)` devuelve 2 tools nativas cuyos nombres son `codemode_search` y `codemode_run`, y invocar la de `run` por la API del framework con `code="len(await get_rows(n=3))"` devuelve un texto que contiene `3`.
- [ ] **Step 2:** Run `uv run --extra all pytest tests/adapters -v` → FAIL.
- [ ] **Step 3:** Implementar cada adaptador como traducción fina de `NeutralTool` (calcar los adaptadores de `astromesh_a2a/adapters/`).
- [ ] **Step 4:** Run → PASS (los que no tienen el framework instalado se saltean; en CI corren todos con `--extra all`).
- [ ] **Step 5: Commit** `feat: adaptadores para 8 frameworks`.

### Task 7: Proxy MCP y CLI

**Files:**
- Create: `astromesh_codemode/mcp_server.py`, `astromesh_codemode/cli.py`, `examples/upstream.yaml`
- Modify: `pyproject.toml` (`[project.scripts] astromesh-codemode = "astromesh_codemode.cli:main"`; `pyyaml` al extra `mcp`)
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Produces: `async build_server(config: ProxyConfig) -> mcp.server.FastMCP`; `ProxyConfig.from_yaml(path)` con `upstreams: list[{name, command, args, url, read_only: list[str]}]`, `name`, `limits`. CLI: `astromesh-codemode mcp --config <path>` (stdio).

- [ ] **Step 1: Tests**: con un upstream FastMCP en memoria de 3 tools, el servidor proxy expone exactamente 2 tools (`codemode_search`, `codemode_run`); `codemode_run` con un programa que llama a la tool de lectura del upstream devuelve su resultado; la tool sin `readOnlyHint` no aparece en `codemode_search`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementar (prefijo de cada tool = `name` del upstream). **Step 4:** Run → PASS.
- [ ] **Step 5: Commit** `feat: proxy MCP que expone servidores upstream en Code Mode`.

### Task 8: Eval de trampas

**Files:**
- Create: `astromesh_codemode/eval/__init__.py`, `eval/traps.py`, `eval/__main__.py` (subcomando `traps`)
- Modify: `.github/workflows/ci.yml` (paso `uv run python -m astromesh_codemode.eval traps`)
- Test: `tests/test_traps.py`; Doc: `docs/eval.md` (sección trampas)

**Interfaces:**
- Produces: `async run_traps(limits: Limits = Limits()) -> TrapReport` con `total: int`, `stopped: int`, `by_trap: dict[str, bool]`, `details: dict[str, str]`. CLI sale con 1 si `stopped < total`.

- [ ] **Step 1: Test** `test_all_traps_stopped_by_default`: `report.total == 11` y `report.stopped == 11`; claves de `by_trap` exactamente: `os_import`, `file_read`, `network`, `infinite_loop`, `memory_bomb`, `deep_recursion`, `unknown_tool`, `bad_args`, `output_flood` (intenta sacar 100 MB), `call_budget`, `excluded_write`. Y `test_lax_limits_let_some_through`: con `Limits(max_calls=10_000, max_output_bytes=10**9)` `call_budget` no se detiene (prueba que el eval detecta fallas, no que todo "pasa").
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementar; "detenida" = el programa no logró su efecto (registrar evidencia en `details`); un error inesperado del host cuenta como **no** detenida. **Step 4:** Run → PASS.
- [ ] **Step 5: Commit** `feat: eval de trampas del sandbox (11/11 en CI)`.

### Task 9: Eval de costo — nivel 1 (sin modelo)

**Files:**
- Create: `astromesh_codemode/eval/cost.py`, `eval/scenarios.py`
- Modify: `pyproject.toml` (extra `eval = ["tiktoken>=0.8", "litellm>=1.50"]`), `eval/__main__.py` (subcomando `cost --level 1`), CI (correr nivel 1)
- Create on run: `results/<fecha>-L1.json`, `results/<fecha>-L1.md`
- Test: `tests/test_cost_l1.py`

**Interfaces:**
- Consumes: `synthetic_catalog(n)` (Task 3), `CodeMode`.
- Produces: `Scenario(catalog_size: int, data: Literal["small","large"])`; `SCENARIOS` = producto de `{8, 64, 512}` × `{"small","large"}`; `async run_level1(scenarios) -> list[Level1Row]` con `strategy: Literal["direct","codemode"]`, `context_tokens: int`, `model_calls: int`.

- [ ] **Step 1: Test** `test_level1_deterministic_and_directional`: dos corridas dan resultados idénticos; para `512/large`, `codemode.context_tokens < direct.context_tokens`; para cada escenario las dos estrategias resuelven la misma respuesta esperada.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implementar. Tarea fija por escenario: "de `list_orders` (5 o 500 filas) quedarse con las 3 de mayor monto y traer el cliente de cada una con `get_customer`". Modelo guionado: *direct* = schemas de todo el catálogo en cada llamada + cada resultado de tool vuelve al contexto; *codemode* = schemas de las 2 tools + salida de `search` + programa + salida de `run`. Tokens con `tiktoken` `o200k_base`.
- [ ] **Step 4:** Run → PASS; `uv run python -m astromesh_codemode.eval cost --level 1` escribe `results/<fecha>-L1.{json,md}`.
- [ ] **Step 5: Commit** `feat: eval de costo nivel 1` (con los resultados generados).

### Task 10: Eval de costo — nivel 2 (modelos reales) — **COMPUERTA**

**Files:**
- Modify: `eval/cost.py` (`async run_level2(scenarios, models: list[str], repeats: int = 3) -> list[Level2Row]`), `eval/__main__.py` (`cost --level 2 --models a,b`)
- Create on run: `results/<fecha>-L2.json`, `results/<fecha>-L2.md`; Doc: `docs/eval.md` (sección costo, tabla y cómo reproducir)
- Test: `tests/test_cost_l2.py` (con `litellm` mockeado: no gasta)

**Interfaces:**
- Produces: `Level2Row`: `model`, `scenario`, `strategy`, `success_rate: float`, `model_calls: float`, `tokens_in: float`, `tokens_out: float`, `cost_usd: float`, `latency_s: float` (promedios sobre `repeats`).

- [ ] **Step 1: Test** con `litellm.acompletion` mockeado devolviendo un guion fijo: `run_level2` produce una fila por (modelo × escenario × estrategia), éxito calculado contra la respuesta esperada de `scenarios.py`, y el costo sale de `usage` × precio de `litellm.model_cost`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementar (loop de tool calling real para *direct*; para *codemode* las 2 tools de `CodeMode`; tope 12 llamadas al modelo por intento). **Step 4:** Run → PASS.
- [ ] **Step 5: Correr de verdad** (requiere claves; **pedir al usuario** las variables de entorno y el OK de gasto antes de correr): `uv run --extra eval python -m astromesh_codemode.eval cost --level 2 --models <barato>,<fuerte>`. Esperado: `results/<fecha>-L2.{json,md}` con 12 filas por modelo.
- [ ] **Step 6:** Escribir en `docs/eval.md` y en ambos README la tabla y la conclusión **tal como salió** ("conviene a partir de N tools / datos grandes", o "no ganó en ningún escenario medido").
- [ ] **Step 7: Commit** `docs: resultados del eval de costo nivel 2`.

### Task 11: README, docs, ejemplos, release a PyPI

**Files:**
- Create: `README.md`, `README.es.md` (logo, qué es, instalación, ejemplo de 5 líneas con LangChain, tabla del nivel 2, seguridad = trampas, límites), `docs/{frameworks,sandbox,mcp-proxy,eval}.md`, `examples/{functions_quickstart,langchain_crm,mcp_proxy}.py`, `.github/workflows/release.yml` (trusted publishing como `astromesh-a2a`, envs `pypi`/`testpypi`)
- Modify: `CHANGELOG.md` (`## [0.1.0] - <fecha>`)
- Test: `tests/test_docs_examples.py` (ejecuta los snippets Python de los README, como `astromesh-context`)

- [ ] **Step 1: Test** `test_readme_snippets_run` → FAIL hasta que existan los README.
- [ ] **Step 2:** Escribir README/docs/ejemplos. **Step 3:** Run → PASS; CI completo verde.
- [ ] **Step 4:** Verificar la compuerta: `results/*-L2.md` existe y está citado en ambos README. Si no, **parar**.
- [ ] **Step 5:** Crear el repo `monaccode/astromesh-codemode` (público) y pushear `main`/`develop`; **el usuario** registra el trusted publisher en pypi.org (proyecto `astromesh-codemode`, workflow `release.yml`, env `pypi`) — pedírselo con los datos exactos.
- [ ] **Step 6:** Tag `v0.1.0` anotado → `release.yml` publica; verificar `pip install astromesh-codemode==0.1.0` en un venv limpio y correr `examples/functions_quickstart.py`.
- [ ] **Step 7: Commit/Release** `chore(release): astromesh-codemode 0.1.0`.
