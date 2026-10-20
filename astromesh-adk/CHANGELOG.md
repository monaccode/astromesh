# Changelog

All notable changes to `astromesh-adk` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.1] - 2026-10-20

### Changed
- `remote_a2a` pasa el `context_id` de la sesión a `reply()` (`astromesh-a2a>=0.1.1`) en lugar de
  sembrar el mapa privado `_contexts`.

## [0.7.0] - 2026-10-20

### Added
- **`remote_a2a(card_url, *, api_key_env=None, policy=None, name=None, description=None)`**: un agente A2A remoto (cualquier
  framework) sobre `astromesh-a2a`, con la forma de un agente ADK: `run()`, `stream()` y
  `as_tool()`. Extra nuevo `astromesh-adk[a2a]` (`astromesh-a2a>=0.1,<0.2`); sin él,
  `remote_a2a()` levanta `MissingA2AExtraError` (un `ImportError`) al construir. Sólo el host de
  `card_url` queda permitido; http se rechaza salvo `policy={"allow_insecure_http": True}`;
  `policy` admite `max_bytes`, `timeout`, `accept_parts`, `allow_insecure_http`. Siempre
  `Origin.AGENT`, también como runnable directo. Un `input_required` queda pendiente por sesión y
  la siguiente llamada de esa sesión lo contesta con `reply()` (con llamadas concurrentes en la
  misma sesión, la primera retoma la tarea y las demás abren tareas nuevas). `name` es el nombre
  de la tool (por defecto, el host) y `description` reemplaza la genérica. Como tool devuelve
  `{answer, status, task_id?, pending?}` con lo remoto envuelto como no confiable (sus `data`
  adentro del bloque) y un remoto caído es una observación de error; como runnable, `RunResult`
  con `metadata` (`status`, `task_id`, `data`, `usage_remoto`…) y errores como `RemoteError`.
  `cost` es 0 salvo que el remoto informe una parte `{"usage": {...}}`; como tool ese uso va al
  span (`a2a.usage_remoto`), no al costo del padre.

### Fixed
- **Las llamadas remotas declaran `origen: "agente"`.** `run_remote` y `stream_remote`
  (`bind()`/`connect()`/`remote()`, incluido un agente remoto usado como tool) mandan
  `origen: "agente"` al nodo, que ya no toma el "si" del modelo padre como confirmación humana de
  una tool con `requires_approval`. Cierra el límite documentado en 0.6.0. La protección requiere
  un nodo >= 0.73; un nodo anterior ignora el campo.

## [0.6.0] - 2026-10-17

### Added
- **Confirmación local con `requires_approval` y `mode="propose"`.** Las corridas locales usan
  la compuerta del core (`astromesh.runtime.confirmacion`): una tool con
  `requires_approval=True` no se ejecuta hasta que la persona re-corre la misma sesión con
  "si" y el modelo repite la llamada exacta (la misma forma que en remoto); la respuesta lleva
  el aviso de qué se va a ejecutar. `@tool(mode="propose")` no ejecuta: la llamada sale en
  `RunResult.propuestas` con `tipo: "adk"`. Los miembros de un equipo y los agentes usados como
  tool (`as_tool()`) corren como sub-corridas de la misma sesión: no confirman ni proponen, y
  su aviso sale en la respuesta que lee la persona. `mode` inválido es `ValueError`.
  Límite: un agente remoto (`bind()`/`connect()`/`remote()`) usado como tool corre en su nodo
  como turno de persona en la sesión `"default"`, así que el modelo padre puede confirmarle
  con "si"; las tools que necesitan aprobación van en el agente que habla con la persona.

### Changed
- **Equipos `swarm` con handoff por tool call.** El agente de entrada recibe a los miembros
  como tools y pasar el control es llamarlas; la respuesta del miembro es la respuesta del
  equipo (core `SwarmPattern(workers=...)`, que trae el historial al destino y
  `max_handoffs`). Se elimina `AgentTeam._build_agent_configs`.

## [0.5.0] - 2026-10-16

Al día con el core 0.70.0. El modo local reusa componentes del core en vez de copiarlos.

### Added
- **Guardrails aplicados en corridas locales.** `guardrails=` se ejecuta con el
  `GuardrailsEngine` del core (0.70): reglas de entrada antes de memoria y modelo, de salida
  sobre la respuesta y los pasos, `cost_limit` antes de cada llamada al modelo. Un bloqueo no es
  un error: `RunResult.blocked=True`, `answer` es el mensaje de rechazo y `guardrail` dice
  `{direction, rule, reason}`. La entrada bloqueada no entra al historial. Hasta ahora la config
  se guardaba y no se aplicaba.
  En los equipos `supervisor` y `swarm` rigen las reglas del supervisor / agente de entrada
  (entrada, salida y `cost_limit` de sus llamadas); en `pipeline` y `parallel` el bloqueo de un
  miembro llega al resultado del equipo, y un `pipeline` se corta en la etapa bloqueada (el
  rechazo no pasa como query a la siguiente).
- `RunResult.blocked`, `guardrail`, `propuestas` y `by_model` (el `usage.by_model` del core, con
  `tokens_cached`). El modo remoto los copia de la respuesta del nodo (`/run` y el `done` del WS);
  el local calcula `by_model` del trace con `astromesh.api.usage.usage_from_trace` (los spans
  `llm.complete` llevan `provider` y `cached_tokens`, como en el core).
- **Modelos por rol:** `@agent(roles={"planner": "...", "synthesizer": "..."})`. Cada rol que
  pide el patrón (`reasoner`, `planner`, `worker`, `synthesizer`, `supervisor`, `stage:<x>`) va a
  su modelo; los demás al `model` del agente. Antes `role=` se ignoraba.
- **Tope de resultados de tools:** `@tool(max_result_tokens=N)` y
  `@agent(max_tool_result_tokens=N)` arman el `_presupuesto_tools` que leen los patrones del core
  (default 8000, como el core).
- `@agent(context_window=N)`: con memoria, el historial se recorta al presupuesto como en el core
  (`MemoryManager.fit_history`, 90% de la ventana menos prompt, tools y el `max_tokens` del
  modelo — 1024 si no lo declara). Sin el parámetro se intenta la ventana de litellm; si no se
  conoce, no se recorta.
- `kb_tools(path)`: las tools `kb_index`/`kb_read`/`kb_find` del core sobre un bundle OKF
  (`tools=[*kb_tools("./kb")]`).
- `pattern="supervisor"` para un agente suelto: sus trabajadores son las tools hechas con
  `otro_agente.as_tool()`. `stages=` para `pattern="pipeline"`.

### Changed
- **Un `pattern` desconocido levanta `AgentConfigError`** al definir el agente, como el core
  0.65. Antes caía en silencio a `react`.
- `guardrails.py` ya no tiene acciones por defecto propias (eran las anteriores a 0.70:
  `cost_limit`/`topic_filter`/`max_length: block`): la forma corta `["pii_detection"]` se
  expande a `{"type": "pii_detection"}` y la acción por defecto la pone el core.
- Los patrones reciben las tools como specs de function calling, como en el core.
- Piso del core `astromesh>=0.70.0`.

### Fixed
- `AgentTeam(pattern="supervisor")` volvió a delegar: desde el core 0.65 el supervisor delega
  llamando a sus trabajadores como tools, y el ADK le pasaba la lista vacía.

## [0.4.0] - 2026-09-28

### Added
- **Ejecución remota por nombre.** Con una conexión en efecto (`agent.bind()`, `remote()` o
  `connect()`, en ese orden), `run()` llama a `POST /v1/agents/{name}/run` del nodo y `stream()`
  a su WebSocket, con la API key como `Authorization: Bearer` y `X-API-Key`; devuelven el mismo
  `RunResult`/`StreamEvent` (con `propuestas` en `metadata`). El agente tiene que estar desplegado
  en el nodo con ese nombre: las `@tool` locales no viajan. 404 → `AgentNotFoundError`, error del
  nodo → `RemoteError`, nodo inalcanzable → `RemoteUnavailableError`. Hasta ahora la conexión se
  guardaba y se ignoraba: todo corría local (`astromesh_adk/_remote.py`).

### Fixed
- **`get_connection()` ve la conexión de `connect()` desde cualquier tarea.** `connect()` escribía
  un contextvar, invisible para las tareas asyncio ya creadas, y la global que la función decía
  consultar nunca se leía. Ahora el contextvar es sólo de `remote()`.

### Changed
- Nueva dependencia directa `websockets>=13.0` (ya llegaba con el core vía `uvicorn[standard]`).

## [0.3.1] - 2026-09-27

### Changed
- Bumped the `astromesh` core dependency floor to `>=0.59.0` (`pyproject.toml`). No ADK code changes.

## [0.2.1] - 2026-08-10

### Changed
- Bumped the `astromesh` core dependency floor to `>=0.40.0` (`pyproject.toml`).

## [0.1.9] - 2026-07-10

### Added
- `@tool` decorator now supports a single Pydantic `BaseModel` parameter (e.g. `def fn(input: MyModel)`): the auto-generated JSON schema is `MyModel.model_json_schema()` instead of degrading to `"string"`, and the wrapper accepts the model's field names as kwargs (constructing the model before calling the function) — matches how LLMs naturally call tools whose params are typed as Pydantic models. Previously a Pydantic param degraded silently and the function received a string at runtime, raising `'str' object has no attribute …` on field access (`astromesh_adk/tools.py`)

### Changed
- Raised the `astromesh` floor to `>=0.29.0`. `ADKRuntime` bridges to the core `ModelRouter`, so ADK runs now transitively gain **per-role model routing** (patterns request `reasoner`/`planner`/`worker`/`synthesizer`/`supervisor` roles, undefined roles fall back to `default`) and the **LiteLLM** multi-source provider (optional `litellm` extra) (`pyproject.toml`)

### Fixed
- `ADKRuntime._make_model_fn` now accepts the `role` keyword that core orchestration patterns pass as of astromesh 0.29.0 (`model_fn(messages, tools, role=...)`). Without it, every `run_team`/`stream`/class-agent path raised `TypeError: model_fn() got an unexpected keyword argument 'role'` against the new core. The ADK binds a single `ModelRouter` per agent, so the role is accepted for signature compatibility and routed through that one router (`astromesh_adk/runner.py`)

## [0.1.8] - 2026-05-22

### Added
- The ADK runner now invokes the `Callbacks` API during execution: `on_tool_result` fires after each tool call and `on_error` on a tool failure, threaded through `run_team → _run_member → run_agent → _make_tool_fn`. Callback invocations are guarded so a faulty callback cannot break a run. Previously `callbacks` was accepted by `run_agent`/`run_team` but never invoked (`astromesh_adk/runner.py`)

## [0.1.7] - 2026-05-20

### Fixed
- `resolve_provider` now passes the provider endpoint as `base_url` (and `api_key_env`) so non-default providers (notably `anthropic` → `https://api.anthropic.com/v1`) actually reach their configured endpoint instead of silently falling back to the OpenAI default (`astromesh_adk/providers.py`)

### Added
- `astromesh_adk.runner.ADKRuntime` — in-process runtime bridging ADK abstractions (`AgentWrapper`/`Agent`/`AgentTeam`) to the Astromesh core engine (orchestration patterns, `ModelRouter`, providers, tracing). Includes `_provider_and_model` model→provider mapping, `_make_model_fn` (router + fallback + system-prompt injection + `llm.complete` span), `_make_tool_fn` (`tool.call` span), and `_build_context` (`astromesh_adk/runner.py`)
- `ADKRuntime.run_agent` — executes a single agent through the core orchestration pattern (ReAct default) under an `agent.run` root span; returns a `RunResult` with cost/token/latency accounting from the trace (`astromesh_adk/runner.py`)
- `ADKRuntime.run_team` — `parallel` (concurrent fan-out, aggregated tokens/cost/spans) and `pipeline` (sequential, answer threaded stage→stage, nested `AgentTeam` supported) orchestration of multi-agent teams (`astromesh_adk/runner.py`)
- `ADKRuntime.run_team` `supervisor` and `swarm` patterns — supervisor/entry agent drives the core pattern with a delegating tool_fn that runs worker agents via `run_agent` (`astromesh_adk/runner.py`)
- `ADKRuntime.stream_agent`/`stream_class_agent` (StreamEvent step/done) and `run_class_agent` (class `Agent` lifecycle hooks on_before_run/on_after_run) (`astromesh_adk/runner.py`)

### Notes
- This release replaces the `_run_local` / `_run_parallel` / `_run_pipeline` / `_run_supervisor` MVP implementation that was version-bumped to 0.1.7 on `main` but never published to PyPI. The new implementation reuses Astromesh core orchestration patterns and the `ModelRouter` instead of duplicating that logic inside the ADK.
