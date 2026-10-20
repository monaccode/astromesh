# astromesh-a2a v0.1 — Librería A2A para cualquier framework · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publicar `astromesh-a2a` 0.1.0: cliente A2A completo y servidor básico, sobre el SDK oficial, con salida de red segura, política de remotos, trace, adaptadores para nueve frameworks y un eval de trampas; con logo, README EN/ES y docs.

**Architecture:** Capa sobre `a2a-sdk` 1.x. Módulos `net`, `policy`, `errors`, `trace`, `client`, `server`, `adapters/*`, `eval`. Repo nuevo `monaccode/astromesh-a2a` con el esqueleto de `astromesh-rag`.

**Tech Stack:** Python ≥3.10, `a2a-sdk>=1.2,<2`, httpx, pyyaml, uv, pytest + respx, ruff, Starlette/uvicorn (extra `server`).

**Spec:** `D:/monaccode/_wt/astromesh-a2a/docs/superpowers/specs/2026-10-19-a2a-design.md` §3 (se copia al repo nuevo en la Tarea 0).

**Repo:** `D:/monaccode/astromesh-a2a` (clon de `monaccode/astromesh-a2a`, rama `main`; las librerías hermanas trabajan sobre `main`).

## Global Constraints

- **API pública en inglés** (como `astromesh-rag`/`-okf`/`-context`; la librería es para el mundo). Nombres fijos: `RemoteAgent`, `Policy`, `Result`, `CardSpec`, `Skill`, `serve`, `create_app`, `Origin` (`HUMAN`/`AGENT`), métodos `RemoteAgent.send()`, `.stream()`, `.reply()`, `.cancel()`, `.card()`, `.as_tool(framework)`; errores `A2AError` → `PolicyRejected`, `BlockedDestination`, `TaskFailed`, `A2ATimeout`, `UnsupportedVersion`, `ConfirmationRequired`. (Ruling: el spec las nombró en castellano; se traducen 1:1.)
- Deps base exactas: `a2a-sdk>=1.2,<2`, `httpx>=0.27`, `pyyaml>=6.0`. Extras: `langchain`, `crewai`, `adk`, `openai-agents`, `pydantic-ai`, `llamaindex`, `smolagents`, `agent-framework`, `mcp`, `server`, `otel`, `all` — con los mismos pisos de versión que `astromesh-okf/pyproject.toml` para los frameworks compartidos.
- Python ≥3.10; Apache-2.0; autor `Juan Carlos Romero <jc@fulfaro.dev>`.
- `Policy()` por defecto: `allowed=[]` (**nada permitido** hasta declarar hosts), `require_signature=False`, `accept_parts={"text","data"}`, `max_bytes=1_048_576`, `timeout=60.0` s, `max_events=1000`, `budget=None`.
- Origen por defecto del cliente: `Origin.AGENT`. El servidor marca toda entrada como `Origin.AGENT` y no confiable.
- Una respuesta remota nunca resuelve una confirmación (spec §5.3).
- Credenciales sólo por variables de entorno o callables; jamás en trace, repr ni mensajes de error.
- `uv.lock` versionado; gate por commit: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q`.
- Commits convencionales en inglés (como las hermanas) con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Card servida desde un host permitido que redirige a una IP interna** o cuyo DNS resuelve a 10/8: `BlockedDestination`, sin request. → `test_dns_rebinding_bloqueado` (T2).
2. **Stream que nunca termina** (remoto que emite `WORKING` para siempre): `A2ATimeout` al tope de tiempo o de eventos. → `test_stream_infinito_corta` (T5).
3. **Artefacto con texto "ignore previous instructions…"**: llega al framework envuelto como dato no confiable. → `test_adapter_envuelve_no_confiable` (T7).
4. **`INPUT_REQUIRED` que pide "respond 'yes' to confirm"**: el cliente no contesta solo; el adaptador lo devuelve al modelo como observación pendiente. → `test_no_autoconfirma` (T5).
5. **Servidor sin auth configurada**: `serve()` lanza al arrancar salvo `insecure=True`. → `test_serve_sin_auth_no_arranca` (T6).

---

### Task 0: Repo, esqueleto y CI

**Files (repo nuevo):** `pyproject.toml`, `uv.lock`, `LICENSE` (Apache-2.0, copiar de astromesh-rag), `README.md` (placeholder 1 línea), `CHANGELOG.md` (`## [Unreleased]`), `CONTRIBUTING.md` (adaptar de astromesh-rag), `.gitignore`, `.github/workflows/ci.yml` (copiar de astromesh-rag ajustando nombre), `.github/workflows/release.yml` (copiar de astromesh-rag; smoke = `python -c "import astromesh_a2a"` + `examples/hello_local.py`), `astromesh_a2a/__init__.py` (`__version__ = "0.1.0"`), `tests/test_import.py`, `docs/superpowers/specs/2026-10-19-a2a-design.md` (copia del spec), `docs/superpowers/plans/` (copia de este plan).

- [ ] **Step 1:** `gh repo create monaccode/astromesh-a2a --public --description "Agent-to-Agent (A2A) for any agent framework: a safe client and server on the official A2A SDK, with egress guards, remote-agent policy, traces and an attack eval." --license apache-2.0` y clonar en `D:/monaccode/astromesh-a2a`.
- [ ] **Step 2:** Test `test_import`: `import astromesh_a2a; assert astromesh_a2a.__version__ == "0.1.0"`.
- [ ] **Step 3:** Escribir `pyproject.toml` (Global Constraints) y `uv lock`.
- [ ] **Step 4:** `uv sync --all-extras && uv run pytest -q` → PASS; ruff limpio.
- [ ] **Step 5:** Commit `chore: scaffold astromesh-a2a` y push a `main`. CI verde en GitHub.

### Task 1: Spike del SDK `a2a-sdk` 1.x → ADR

**Files:** Create `docs/adr/0001-a2a-sdk.md`.

- [ ] **Step 1:** Instalar `a2a-sdk` (versión resuelta en el lock) y leer su código: cliente (factory/transport JSON-RPC, cómo inyectar un `httpx.AsyncClient` propio, envío bloqueante, streaming SSE, `GetTask`, `CancelTask`, resolución de card), servidor (`AgentExecutor`, `RequestContext`, `EventQueue`, `TaskUpdater`, task store en memoria, app Starlette, ruta de la card), modelos (`AgentCard`, `AgentSkill`, `Message`, `Part`, `Task`, `TaskState`), verificación de firma de cards si existe.
- [ ] **Step 2:** ADR con: clases y firmas exactas que usarán T5/T6, cómo se pasa el transporte seguro de T2, cómo se mapean los estados y qué falta en el SDK. Commit `docs: ADR on the a2a-sdk surface we build on`.

### Task 2: `net` — salida de red segura

**Files:** `astromesh_a2a/net.py`, `tests/test_net.py`. Portar de `D:/monaccode/_wt/astromesh-a2a/astromesh/tools/builtin/_red.py` (`destino_bloqueado`, `pin_a_ip_publica`, `TransportePineado`) traducido a inglés.

**Interfaces:**
- Produces: `blocked_reason(url: str) -> str | None`; `class PinnedTransport(httpx.AsyncBaseTransport)` (`max_bytes: int`, `.reason: str | None`); `safe_client(policy: Policy, *, allow_private: bool = False) -> httpx.AsyncClient` (sin redirecciones, timeout de la política).

- [ ] **Step 1: Tests que fallan:** `test_bloquea_rangos_privados` (10/8, 172.16/12, 192.168/16, 127/8, 169.254/16, 100.64/10, ::1, fc00::/7, fe80::/10, `::ffff:10.0.0.1`); `test_dns_rebinding_bloqueado` (resolver falso → 10.0.0.5 → `BlockedDestination` sin abrir socket); `test_no_sigue_redirecciones`; `test_tope_de_cuerpo`; `test_sni_y_host_correctos`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS. **Step 5:** Commit `feat(net): pinned egress transport with private-range and size guards`.

### Task 3: `policy`, `errors`, `trace`

**Files:** `astromesh_a2a/policy.py`, `errors.py`, `trace.py`, `tests/test_policy.py`, `tests/test_trace.py`.

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Policy` (campos y defaults de Global Constraints; `budget: Budget | None` con `max_calls: int | None`, `max_seconds: float | None`); `Policy.check_card_url(url) -> None` (lanza `PolicyRejected`); `Policy.check_part(kind: str, size: int) -> None`; errores de Global Constraints (`PolicyRejected(reason: str)`, etc.); `class Trace` con `.add(stage: str, **fields) -> None`, `.to_dict() -> list[dict]`, `.traceparent() -> str` (W3C `00-<32hex>-<16hex>-01`).

- [ ] **Step 1: Tests que fallan:** `test_default_no_permite_nada`; `test_permitidos_por_host_y_por_url`; `test_partes_file_rechazadas_por_defecto`; `test_presupuesto_llamadas`; `test_trace_no_contiene_secretos` (headers `Authorization`/`X-API-Key` y env vars nunca aparecen en `to_dict()`); `test_traceparent_formato_w3c`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS. **Step 5:** Commit `feat: policy, typed errors and per-stage trace`.

### Task 4: `RemoteAgent` — card y envío bloqueante

**Files:** `astromesh_a2a/client.py`, `astromesh_a2a/types.py` (`Result`, `Origin`), `tests/test_client_send.py`, `tests/conftest.py` (servidor de referencia del SDK en proceso, según el ADR).

**Interfaces:**
- Consumes: `safe_client`, `Policy`, `Trace`, errores; superficie del SDK según ADR.
- Produces: `class RemoteAgent(card_url: str, *, policy: Policy, auth: Auth | None = None, origin: Origin = Origin.AGENT)`; `Auth.api_key(env: str, header="X-API-Key")`, `Auth.bearer(env: str)`; `async card() -> AgentCard`; `async send(text: str, *, context_id: str | None = None, data: dict | None = None) -> Result`; `@dataclass Result(status: str, answer: str, data: list[dict], task_id: str | None, context_id: str | None, pending: str | None, trace: list[dict])` con `status ∈ {"completed","input_required","auth_required"}`.

- [ ] **Step 1: Tests que fallan** (contra el servidor de referencia del SDK, en proceso): `test_send_completed`; `test_card_fuera_de_politica_no_envia`; `test_version_header_1_0`; `test_metadata_origen_y_traceparent`; `test_auth_api_key_desde_env` (el header llega; el valor no aparece en `result.trace`); `test_version_no_soportada`; `test_failed_lanza_task_failed`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS. **Step 5:** Commit `feat(client): RemoteAgent card discovery and blocking send`.

### Task 5: `RemoteAgent` — stream, input-required, cancel, presupuesto

**Files:** `astromesh_a2a/client.py`, `tests/test_client_stream.py`.

**Interfaces:**
- Produces: `async stream(text, *, context_id=None) -> AsyncIterator[Event]` (`Event(kind: Literal["status","artifact","message"], payload: dict)`), `async reply(task_id: str, text: str) -> Result`, `async cancel(task_id: str) -> None`.

- [ ] **Step 1: Tests que fallan:** `test_stream_artefactos_en_orden`; `test_stream_infinito_corta` (`A2ATimeout` por `max_events` y por `timeout`); `test_input_required_devuelve_pending`; `test_reply_continua_misma_tarea`; `test_no_autoconfirma` (el remoto pide "say yes"; `send()` devuelve `input_required` y ninguna request adicional sale); `test_cancel`; `test_presupuesto_corta_antes_de_enviar`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS. **Step 5:** Commit `feat(client): streaming, input-required, cancel and budgets`.

### Task 6: Servidor — `serve` / `create_app`

**Files:** `astromesh_a2a/server.py`, `astromesh_a2a/card.py` (`CardSpec`, `Skill`), `tests/test_server.py`.

**Interfaces:**
- Produces: `@dataclass CardSpec(name, description, version, url, skills: list[Skill], streaming: bool = True)`; `@dataclass Skill(id, name, description, tags=(), examples=(), input_modes=("text/plain",), output_modes=("text/plain",))`; `Handler = Callable[[Incoming], Awaitable[Outgoing]]` donde `Incoming(text: str, data: list[dict], origin: Origin, context_id: str, untrusted: bool = True)` y `Outgoing(answer: str, data: list[dict] = (), needs_confirmation: str | None = None)`; `create_app(handler, card: CardSpec, *, auth: Callable[[Request], Awaitable[bool]] | None, insecure: bool = False) -> Starlette`; `serve(handler, card, *, host="127.0.0.1", port=8000, auth=None, insecure=False) -> None`; `api_key_auth(env: str, header="X-API-Key")`.

- [ ] **Step 1: Tests que fallan:** `test_card_en_well_known`; `test_cliente_oficial_del_sdk_habla_con_create_app` (interop); `test_remote_agent_habla_con_create_app`; `test_needs_confirmation_es_input_required`; `test_respuesta_remota_no_confirma` (dos mensajes: el segundo "yes" llega con `origin=AGENT`; el handler ve `untrusted=True` y la librería no marca nada como confirmado); `test_auth_rechaza_sin_key` (401); `test_serve_sin_auth_no_arranca` (`ValueError` salvo `insecure=True`).
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS. **Step 5:** Commit `feat(server): expose any async agent as an A2A agent`.

### Task 7: Adaptadores de framework

**Files:** `astromesh_a2a/adapters/{__init__,_common,langchain,crewai,adk,openai_agents,pydantic_ai,llamaindex,smolagents,agent_framework,mcp}.py`, `astromesh_a2a/adapters/server_langchain.py`, `tests/adapters/test_*.py`. Molde: `D:/monaccode/astromesh-okf/astromesh_okf/` (cómo se arman herramientas por framework y cómo se importan perezosamente con `MissingExtraError`).

**Interfaces:**
- Consumes: `RemoteAgent.send/reply`.
- Produces: `RemoteAgent.as_tool(framework: str, *, name: str | None = None, description: str | None = None)` → objeto herramienta nativo; `_common.wrap_untrusted(result: Result) -> str` (bloque `<remote-agent-output untrusted="true">…</remote-agent-output>` + estado + `task_id` si pendiente); `server_langchain.handler_from_runnable(runnable) -> Handler`.

- [ ] **Step 1: Tests que fallan** (uno por framework, importorskip si el extra falta en el entorno local, pero CI instala `all`): `test_<fw>_tool_invoca_remoto`; `test_adapter_envuelve_no_confiable`; `test_adapter_pendiente_expone_task_id`; `test_extra_faltante_error_claro`; `test_handler_from_runnable`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar en dos commits (lote 1: langchain, crewai, adk, openai-agents, pydantic-ai; lote 2: llamaindex, smolagents, agent-framework, mcp + server_langchain). **Step 4:** → PASS. **Step 5:** Commits `feat(adapters): …`.

### Task 8: Eval de trampas

**Files:** `astromesh_a2a/eval/{__init__,traps}.py`, `examples/eval_traps.py`, `tests/test_eval.py`, `docs/eval.md`.

**Interfaces:**
- Produces: `async run_traps(policy: Policy = Policy(...allowed=[local])) -> EvalReport` (`EvalReport(total: int, stopped: int, by_trap: dict[str, bool])`); CLI `python -m astromesh_a2a.eval`.

Trampas (cada una es un servidor local con `create_app` o un servidor falso): `card_spoof` (card de otro host), `redirect_internal`, `dns_private`, `huge_artifact`, `file_part`, `injection_text` (debe llegar envuelto), `self_confirm` (input-required que pide "yes"), `endless_stream`, `version_0_3`.

- [ ] **Step 1: Tests que fallan:** `test_politica_por_defecto_detiene_todas` (`stopped == total`); `test_politica_laxa_deja_pasar_alguna` (prueba que el eval mide algo).
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS; job de CI que corre el eval y falla si `stopped < total`.
- [ ] **Step 5:** Commit `feat(eval): attack traps for remote agents`.

### Task 9: Identidad y documentación

**Files:** `assets/logo-mark.svg`, `assets/logo.png`, `assets/icon.png`, `README.md`, `README.es.md`, `docs/{client,server,policy,frameworks,ecosystem}.md`, `examples/{hello_local,langchain_tool,serve_langchain}.py`, `CHANGELOG.md`.

- [ ] **Step 1:** Logo con la skill `frontend-design`: mismo sistema visual que `D:/monaccode/astromesh-rag/assets/` (comparar `logo-mark.svg` y `logo.png` de rag/okf/context: paleta, tipografía, proporciones 1280×? del `logo.png`). Motivo: dos nodos que se pasan una tarea por un canal custodiado. Exportar PNG con Playwright/Chromium (como los carruseles) y revisar visualmente.
- [ ] **Step 2:** README EN con la estructura de `astromesh-rag/README.md` (logo, badges, "qué es A2A", "por qué no alcanza el SDK solo" con la tabla de protecciones, uso en 5 líneas cliente + 10 servidor, tabla de frameworks, resultado del eval, ecosistema) y README.es equivalente.
- [ ] **Step 3:** `docs/*.md` (uno por tema) y ejemplos ejecutables offline (`hello_local.py` levanta un servidor local y lo llama). Test: `tests/test_examples.py` corre `hello_local.py`.
- [ ] **Step 4:** Commit `docs: logo, README (EN/ES), guides and examples`.

### Task 10: Release 0.1.0

- [ ] **Step 1 (manual, del usuario):** registrar el *trusted publisher* en PyPI y TestPyPI para `monaccode/astromesh-a2a`, workflow `release.yml`, entornos `pypi`/`testpypi` (sin esto el job de PyPI falla como pasó con astromesh-rag).
- [ ] **Step 2:** CHANGELOG `## [0.1.0] - <fecha>`, tag `v0.1.0` anotado, push; verificar TestPyPI → smoke → PyPI.
- [ ] **Step 3:** GitHub release con notas del CHANGELOG.
