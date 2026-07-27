# Sync de conocimiento: astromesh core v0.36.0 → LEIA, Cortex y CLI

**Fecha:** 2026-07-27
**Estado:** Diseño aprobado (pendiente revisión del spec)
**Driver:** el core (`astromesh`) avanzó de v0.29.0 a **v0.36.0**. Tres consumidores llevan
conocimiento embebido de versiones distintas del core y deben sincronizarse.

## Contexto y motivación

El core es la fuente de verdad del contrato de agentes (schema YAML, respuesta de `/run`,
contrato de streaming WS). Tres proyectos independientes embeben una copia de ese conocimiento y
quedaron desfasados:

| Target | Repo | Última sync | Versión propia |
|---|---|---|---|
| **LEIA** | `astromesh-leia` | core **v0.29.0** | 0.3.0 |
| **Cortex** | `astromesh-cortex` | schema v0.35.0 / eventos v0.34.0 | 0.16.0 |
| **CLI** | `astromesh/astromesh-cli` | pin `astromesh>=0.18.0` | 0.1.1 |

Cada uno se releasa de forma independiente (monorepo de paquetes versionados por separado).

### Delta del core v0.30.0 → v0.36.0 (fuente de verdad)

- **v0.31.0** — RAGPipeline CRUD REST (`/v1/rag/pipelines`), HITL durable (APPROVAL/WAIT/SUSPENDED), PgRunStore.
- **v0.32.0** — `POST /v1/workflows/register` (blueprint dinámico `{workflow, agents, rag_pipelines}`).
- **v0.34.0** — contrato de streaming: `on_event` emite `{type: token|tool_call|tool_result}`; WS `/v1/ws/agent/{name}` vivo; `done` = `{answer, session_id, usage}`.
- **v0.35.0** — `type: client` (tool anunciada, no ejecutada; entregada por el streaming). Los tipos **cargables desde YAML** son **solo `builtin | agent | client`**; `internal/mcp/webhook/rag` nunca cargaron y ahora logean WARNING. Normalización del shorthand de `parameters`.
- **v0.35.1** — `timeout` llega a `openai_compat`.
- **v0.36.0** — `parameters` llega a `openai_compat` y `ollama` (bajo `options`); el model block avisa de keys que su source ignora; **`usage.by_model`**: desglose de consumo por `(provider, model, role)`.

### Contrato exacto de `usage` (core v0.36.0)

`AgentRunResponse.usage` y el `done` del WS devuelven `UsageInfo`:

```
UsageInfo   { tokens_in: int, tokens_out: int, model: str (compat), by_model: ModelUsage[] }
ModelUsage  { provider: str, model: str, role: str="default", calls: int,
              tokens_in: int, tokens_out: int, cost: float }
```

`model` (plano) es el primer modelo visto, sin valor correcto en corridas multi-modelo; `by_model`
es la atribución autoritativa. No hay `credits`/`infra_cost` en el contrato del core — esa economía
es exclusiva del hub de nexus.

## Alcance por target

### 1. LEIA (`astromesh-leia`) — brecha grande, con bug de conocimiento activo

LEIA le enseña al LLM a **autorear** agentes. Su schema (a v0.29.0) enseña algo **incorrecto** desde
v0.35.0: `schemas/astromesh-v1-agent.md:270` dice "Three types are supported" pero documenta 7
(`builtin, agent, internal, mcp, webhook, rag`), varios de los cuales **no cargan** desde YAML. El
`leia-architect` genera agentes con tools que fallan en silencio. **Es el fix más importante.**

Cambios:

1. **`schemas/astromesh-v1-agent.md` — `spec.tools`.** Reescribir la lista a los cargables
   `builtin | agent | client`. Documentar `type: client` (anunciada, nunca ejecutada; entregada al
   consumidor por los eventos `tool_call`/`tool_result` del streaming; registrada en `steps`).
   Marcar `internal/mcp/webhook/rag` como **no cargables desde agent YAML** (el runtime logea
   WARNING y los omite). Documentar el shorthand de `parameters` y su normalización a JSON Schema.
2. **`schemas/astromesh-v1-agent.md` — model block.** Añadir la matriz "qué key consume/ignora cada
   source" (v0.36.0) y confirmar que `parameters`/`timeout` ahora sí llegan a `ollama` /
   `openai_compat` / `litellm` (antes se descartaban en silencio en varias ramas).
3. **`agents/leia-architect.md`.** Guía: ofrecer `client` tools cuando el valor sea la llamada
   misma (mostrar gráfico, abrir formulario); nunca emitir tipos no cargables.
4. **`schemas/` — contrato de streaming y consumo.** Subsección del contrato de streaming
   (`token`/`tool_call`/`tool_result`, WS vivo v0.34.0) — porque la `client` tool se entrega por ese
   canal — y de `usage.by_model` (v0.36.0), que `leia-doctor` usa para reportar consumo.
5. **`schemas/nexus-api.md` — capacidades nuevas del control plane.** Documentar RAGPipeline CRUD
   (`/v1/rag/pipelines`, v0.31.0) y el registro dinámico de blueprints
   (`POST /v1/workflows/register`, v0.32.0).
6. **`README.md`.** Arreglar la tabla de compatibilidad (stale: 0.2.x/0.28.9) y el link de descarga
   `v0.2.0`; badge → v0.4.0.
7. **Release `0.3.0 → 0.4.0`** (feat: knowledge sync). Version files: `.claude-plugin/plugin.json`,
   badge del README, `CHANGELOG.md`. Merge `develop→main`, tag `v0.4.0`.

### 2. Cortex (`astromesh-cortex`) — brecha chica, feature real

El `agent.schema.json` ya tiene `client` + `timeout` + `parameters` + per-role (al día). El delta
real es **`usage.by_model`**: hoy `RunUsage` es plano y no lo representa.

Cambios:

1. **`src/services/agent-run-events.ts`.** Añadir `RunModelUsage { provider, model, role, calls,
   tokens_in, tokens_out, cost }` y `by_model?: RunModelUsage[] | null` a `RunUsage`; extender
   `isRunUsage` para validar/guardar el arreglo (nullable, opcional — un runtime pre-v0.36 no lo
   envía).
2. **`src/types/api.ts:128`.** Reflejar `by_model` en la forma inline de `usage` de la respuesta
   HTTP.
3. **`src/components/console/AgentConsole.tsx`.** Desglose por modelo **estilo UsoPanel** para
   corridas directas cuando `by_model` venga: tabla provider/model/role/calls/tokens/cost, reusando
   el lenguaje visual del `UsoPanel` del hub. (Sin credits/infra: el core no los expone.)
4. **Version refs.** README ecosystem table `v0.35.1 → v0.36.0`; sellos de comentarios que
   correspondan.
5. **Release `0.16.0 → 0.17.0`.** `CHANGELOG.md` `[Unreleased]` → 0.17.0, `package.json`. Merge
   `develop→main`, tag `v0.17.0`.

### 3. CLI (`astromesh/astromesh-cli`) — mecánico + feature

1. **`pyproject.toml:12`.** Pin `astromesh>=0.18.0 → >=0.36.0` (el path source editable no cambia).
2. **`astromesh_cli/commands/run.py:53,59`.** Hoy lee `data.get("tokens_used")` — campo **stale**:
   el run response devuelve `usage: UsageInfo`. Leer `usage.tokens_in/tokens_out` y renderizar
   `usage.by_model` (tabla por modelo), con fallback al total plano.
3. **`astromesh_cli/main.py` — `version`.** Que además reporte la versión del core `astromesh`
   instalado (hoy solo muestra la del CLI).
4. **Crear `astromesh-cli/CHANGELOG.md`** (Keep a Changelog) — no existe.
5. **Release `0.1.1 → 0.2.0`.** `pyproject.toml` + `astromesh_cli/__init__.py`. Sub-paquete del
   monorepo → **commit `chore(release): astromesh-cli 0.2.0`** en `develop` de `astromesh`, **sin
   tag propio** (los tags anotados son del core). Se integra a `main` en el flujo normal del repo.

## Fuera de alcance

- No se toca el core (`astromesh`): ya está en v0.36.0 y es la fuente. El único cambio en el repo
  core es el sub-paquete CLI y este spec.
- Streaming WebSocket en el CLI (hoy es REST puro): net-new grande, no requerido para el sync.
- Economía de credits/infra en las vistas de Cortex de corridas directas: el core no la expone.

## Orquestación / orden

LEIA (mayor valor) → Cortex → CLI. Cada track, independiente:

1. Cambios de contenido/código.
2. Self-review + tests/lint del repo (gate verde).
3. Code review (skill `requesting-code-review`).
4. CHANGELOG + bump de versión.
5. Merge `develop→main` + tag (LEIA/Cortex; el CLI es commit de release sin tag).
6. **Push solo cuando el usuario confirme**; verificar CI verde tras cada push.

## Testing / verificación por repo

- **LEIA:** `validate` plugin (workflow del repo) + revisión manual de que ningún ejemplo/esquema
  siga sugiriendo tipos no cargables; los 6 templates siguen siendo single-model Ollama (deploy
  as-is).
- **Cortex:** `vitest` (gate actual ~243 tests) + `tsc` + lint; test nuevo de `isRunUsage` con
  `by_model` presente/ausente y de render del desglose.
- **CLI:** `uv run pytest` del sub-paquete; test de `run` renderizando `usage.by_model` y del
  fallback plano.

## Riesgos

- **LEIA (mayor):** cambiar la lista de tipos altera lo que el architect genera. Mitigación: el
  cambio corrige a lo que el runtime realmente carga; los templates existentes no usan tipos no
  cargables.
- **Cortex:** `by_model` opcional/nullable evita romper contra runtimes pre-v0.36.
- **CLI:** `run.py` ya leía un campo stale (`tokens_used`); el cambio lo corrige. Verificar la forma
  real de la respuesta contra el core antes de editar.
