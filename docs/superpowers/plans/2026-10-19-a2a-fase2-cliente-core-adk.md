# A2A Fase 2 — Cliente A2A en el core, Forge y ADK · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un agente de Astromesh use agentes A2A remotos como herramienta (`type: a2a`) y que el ADK ofrezca `remote_a2a()`, ambos sobre `astromesh-a2a`; cerrar con el release core 0.73.0 y ADK.

**Architecture:** Extra `a2a` del core = `astromesh-a2a`. Nuevo `ToolType.A2A` con handler que construye un `RemoteAgent` por herramienta (política desde el YAML), recuerda el `task_id` pendiente por sesión y devuelve al modelo `INPUT_REQUIRED` como observación. Forge y schema lo exponen. El ADK suma `remote_a2a(card_url, ...)`.

**Tech Stack:** Python 3.12, `astromesh-a2a>=0.1,<0.2`, pytest, respx.

**Spec:** `D:/monaccode/_wt/astromesh-a2a/docs/superpowers/specs/2026-10-19-a2a-design.md` §4 fase 2. **Depende de:** plan de la librería (0.1.0 publicada) y fase 0.

**Rama:** `feat/a2a` (mismo worktree que la fase 0).

## Global Constraints

- YAML de la herramienta:
  ```yaml
  - name: agenda_externa
    type: a2a
    card_url: https://agentes.ejemplo.com/.well-known/agent-card.json
    auth: {api_key_env: AGENDA_KEY}        # o {bearer_env: ...}; opcional
    policy: {max_bytes: 262144, timeout: 30, accept_parts: [text, data]}  # opcional
    description: "…"                        # opcional; si falta, se usa la de la card
  ```
  El host de `card_url` queda permitido automáticamente; nada más lo está.
- La herramienta acepta `{query: string}` (como `type: agent`) y devuelve `{answer, data?, status, task_id?, pending?}`; la salida remota llega envuelta como no confiable (`wrap_untrusted` de la librería).
- Un `task_id` pendiente (`input_required`) se guarda por `(session_id, tool)`; la siguiente invocación de la misma herramienta en esa sesión llama `reply(task_id, query)`.
- La herramienta corre siempre con `Origin.AGENT`.
- Extra del core: `a2a = ["astromesh-a2a>=0.1,<0.2"]`, incluido en `all`; `uv lock` en raíz (`astromesh-node`/`astromesh-cli` no cambian salvo versión en el release).
- Gates y CHANGELOG como la fase 0.

## Review Focus

1. **Extra `a2a` no instalado** y un agente declara `type: a2a`: error claro al cargar el agente ("instalá astromesh[a2a]"), no un ImportError en la primera llamada. → `test_sin_extra_error_al_cargar` (T1).
2. **Dos sesiones simultáneas** con la misma herramienta pendiente: cada una retoma su propio `task_id`. → `test_pendientes_por_sesion` (T1).
3. **Remoto caído**: observación de error para el modelo, sin tumbar el run del padre. → `test_remoto_caido_es_observacion` (T1).
4. **`card_url` http (no https)**: rechazado salvo `allow_insecure_http: true` explícito. → `test_http_rechazado` (T1).
5. **Costo informado por el remoto** (metadata de usage): queda en el trace de la herramienta, no se suma al `by_model` (no es un modelo nuestro). → `test_costo_remoto_en_trace` (T1).

---

### Task 1: `type: a2a` en el runtime

**Files:** `astromesh/core/tools.py` (`ToolType.A2A`, rama de ejecución), `astromesh/runtime/engine.py` (rama de wiring ~L943-1194, `_CLAVES_POR_TIPO`), `astromesh/integrations/a2a.py` (crear: construcción de `RemoteAgent` y estado pendiente), `pyproject.toml` (extra), `uv.lock`, `tests/test_tool_a2a.py`.

**Interfaces:**
- Consumes: `astromesh_a2a.RemoteAgent`, `Policy`, `Auth`, `Result`, `wrap_untrusted`.
- Produces: `ToolType.A2A`; `build_a2a_tool(cfg: dict) -> ToolDefinition`.

- [ ] **Step 1: Tests que fallan** (servidor local con `astromesh_a2a.create_app`): `test_a2a_tool_completed`; `test_a2a_input_required_y_reply`; `test_pendientes_por_sesion`; `test_remoto_caido_es_observacion`; `test_sin_extra_error_al_cargar`; `test_http_rechazado`; `test_costo_remoto_en_trace`; `test_salida_envuelta_no_confiable`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS; suite completa. **Step 5:** CHANGELOG + commit `feat(tools): type a2a — agentes A2A remotos como herramienta`.

### Task 2: Schema, Forge y docs

**Files:** `vscode-extension/schemas/agent.schema.json` (tool `type: a2a` y sus claves), `astromesh-forge/src/types/agent.ts`, `astromesh-forge/src/utils/tools.ts` (opción en el selector + `READS_DESCRIPTION`), `docs/CONFIGURATION_GUIDE.md`, `docs-site/src/content/docs/configuration/multi-agent.md` (sección A2A), `docs-site` página del ecosistema (ficha `astromesh-a2a`).

- [ ] **Step 1: Tests que fallan:** `test_schema_acepta_tool_a2a`; test de Forge del selector (vitest) si existe el patrón.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS. **Step 5:** Commit `feat(forge,docs): herramienta a2a en schema, Forge y docs`.

### Task 3: `remote_a2a()` en el ADK

**Files:** `astromesh-adk/astromesh_adk/connection.py` (o módulo nuevo `_a2a.py`), `astromesh-adk/pyproject.toml` (extra `a2a`), `astromesh-adk/tests/test_remote_a2a.py`, `docs-site/src/content/docs/adk/remote-execution.mdx`, `astromesh-adk/CHANGELOG.md`.

**Interfaces:**
- Produces: `remote_a2a(card_url: str, *, api_key_env: str | None = None, policy: dict | None = None)` — mismo contrato de uso que `remote()` (agente usable como tool o runnable), resultado con `cost` = 0 salvo que el remoto informe usage.

- [ ] **Step 1: Tests que fallan:** `test_remote_a2a_run`; `test_remote_a2a_stream`; `test_remote_a2a_input_required`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS. **Step 5:** Commit `feat(adk): remote_a2a sobre astromesh-a2a`.

### Task 4: Releases

- [ ] **Step 1:** Release core **0.73.0** según "Release Checklist" de CLAUDE.md (versión en pyproject ×2 y `__init__`; tres `uv.lock` editando sólo la versión —no regenerar con un uv más nuevo que el del repo—; CHANGELOG; tag `v0.73.0` anotado; PyPI). Incluye fase 0 + fase 2.
- [ ] **Step 2:** Release ADK (versión en pyproject + `__init__`, CHANGELOG, tag `adk-v*`).
- [ ] **Step 3:** `develop` y `main` del core quedan iguales (fast-forward).
