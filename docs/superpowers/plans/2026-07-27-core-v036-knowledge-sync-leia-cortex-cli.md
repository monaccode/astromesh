# Sync de conocimiento core v0.36.0 → LEIA · Cortex · CLI — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Propagar el contrato de astromesh core v0.36.0 (tool types cargables + `type: client`, `usage.by_model`, streaming, RAGPipeline CRUD + workflows/register) a los tres consumidores que llevan conocimiento embebido desfasado, y releasar cada uno.

**Architecture:** Tres tracks independientes, uno por repo, cada uno con su propio ciclo de test/review/release. LEIA = edición de conocimiento (markdown) verificada por grep + el workflow `validate`. Cortex = TypeScript/vitest (tipo + validación + UI). CLI = Python/pytest (pin + render defensivo). No se toca el core salvo el sub-paquete CLI.

**Tech Stack:** Markdown (LEIA plugin), TypeScript + React + vitest (Cortex/Electron), Python 3.12 + typer + rich + pytest (CLI).

## Global Constraints

- **Contrato `usage` del core v0.36.0 (verbatim):** `UsageInfo { tokens_in:int, tokens_out:int, model:str, by_model: ModelUsage[] }`; `ModelUsage { provider:str, model:str, role:str="default", calls:int, tokens_in:int, tokens_out:int, cost:float }`. Sin `credits`/`infra_cost` (eso es solo del hub de nexus).
- **Tool types cargables desde agent YAML (verbatim):** solo `builtin | agent | client`. `internal`, `mcp*`, `webhook`, `rag` **no cargan** — el runtime logea WARNING y los omite.
- **`type: client`:** anunciada al modelo, **nunca ejecutada** por el runtime; entregada al consumidor por los eventos `tool_call`/`tool_result` del streaming y registrada en `steps`. `ToolRegistry.execute()` devuelve `{"ok": True}` sin correr nada.
- **`by_model` es opcional/nullable** en todo consumidor: un runtime pre-v0.36 no lo envía; nunca asumir su presencia.
- **Commits:** conventional commits. `feat:`/`fix:`/`refactor:` requieren entrada de CHANGELOG en el mismo commit o inmediatamente antes.
- **Push:** NO pushear ni mergear a `main` hasta que el usuario lo confirme. Tras cada push, verificar CI verde.
- **Co-Autoría en commits:** terminar cada mensaje de commit con `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

# Track A — LEIA (`astromesh-leia`) → v0.4.0

Repo: `/Users/fulfaro/monaccode/astromesh-leia`. Branch de trabajo: `develop`. No hay tests unitarios; la verificación es grep + el workflow `validate` del repo. Cada task commitea en `develop`.

### Task A1: Reescribir `spec.tools` a los tipos cargables + `type: client`

**Files:**
- Modify: `schemas/astromesh-v1-agent.md:268-341` (sección `## spec.tools`)

**Interfaces:**
- Produces: la sección `spec.tools` con la lista correcta `builtin | agent | client`, la subsección `Type: client`, y una nota de tipos no cargables. Task A3 (leia-architect) referencia esta sección.

- [ ] **Step 1 (verificación previa):** Confirmar el texto stale.

Run: `grep -n "Three types are supported" schemas/astromesh-v1-agent.md`
Expected: coincide en la línea 270.

- [ ] **Step 2:** Reemplazar el bloque de la línea 270 (`Array of tool definitions...`) hasta el final de `### Type: rag` (línea 339, justo antes de la nota `> Common per-tool fields`) por el siguiente contenido:

```markdown
Array of tool definitions. Each tool must have a `type` field. Only **three**
tool types can be loaded from an agent YAML file: `builtin`, `agent`, and
`client`. Any other `type` value (`internal`, `mcp_stdio`/`mcp_sse`/`mcp_http`,
`webhook`, `rag`) is **not loadable from YAML** — the runtime logs a `WARNING`
naming the agent, the tool and the unsupported type, and skips the tool (it is
never registered, never reaches the model). From astromesh core 1.0 an
unsupported type becomes a hard error. Do not author agents with those types.

### Type: builtin

Pre-packaged tools provided by the astromesh runtime.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | REQUIRED | -- | Must be `"builtin"`. |
| `name` | string | REQUIRED | -- | Built-in tool name (e.g., `web_search`, `calculator`, `datetime`, `http_request`). |
| `config` | object | optional | `{}` | Tool-specific configuration. |
| `rate_limit` | object | optional | -- | Rate limiting: `{max_calls: int, period_seconds: int}`. |

### Type: agent

Delegates to another deployed agent as a tool.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | REQUIRED | -- | Must be `"agent"`. |
| `name` | string | REQUIRED | -- | Tool name as exposed to the LLM. |
| `agent` | string | REQUIRED | -- | `metadata.name` of the target agent. Must be deployed in the same namespace. |
| `description` | string | optional | target agent's `spec.identity.description` | Override description for the tool. |
| `parameters` | object | optional | -- | Input parameters. Accepts the shorthand `{param: {type, description}}` (the runtime normalizes it into valid JSON Schema) or a full JSON Schema object. |
| `context_transform` | string | optional | -- | Jinja2 template to transform context before passing to the sub-agent. |
| `rate_limit` | object | optional | -- | Rate limiting: `{max_calls: int, period_seconds: int}`. |

### Type: client (astromesh core v0.35.0+)

A tool the runtime **announces to the model but never executes**. The point of
the call is the call itself — "show this chart", "open this form" — and what it
means is the consumer's business, not the runtime's. When the model calls a
`client` tool the runtime returns `{"ok": true}` without running anything; the
call is delivered live to the consumer through the streaming `tool_call` /
`tool_result` events (see *Streaming contract* below) and recorded afterwards in
the run's `steps` (`action` / `action_input`). With nobody listening a `client`
tool is a silent no-op — that is correct, not a bug.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | REQUIRED | -- | Must be `"client"`. |
| `name` | string | REQUIRED | -- | Tool name as exposed to the LLM. |
| `description` | string | REQUIRED | -- | What the call means to the consumer. |
| `parameters` | object | optional | -- | Input parameters. Shorthand `{param: {type, description}}` is normalized into valid JSON Schema before it reaches the model — required, because a strict provider rejects the whole request on an invalid schema. |
```

- [ ] **Step 3 (verificación):** La lista correcta y `client` están presentes; los tipos viejos ya no se presentan como cargables.

Run: `grep -nE "Type: client|not loadable from YAML|Type: internal|Type: rag" schemas/astromesh-v1-agent.md`
Expected: aparecen `Type: client` y `not loadable from YAML`; **no** aparecen `### Type: internal`, `### Type: rag`, `### Type: webhook`, `### Type: mcp` como secciones cargables.

- [ ] **Step 4: Commit**

```bash
git add schemas/astromesh-v1-agent.md
git commit -m "docs(schema): corregir spec.tools a los tipos cargables + type client (core v0.35.0)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task A2: Model block — matriz de keys por source + params/timeout honrados

**Files:**
- Modify: `schemas/astromesh-v1-agent.md` (sección per-role, ~línea 193-202, tras la tabla de candidate fields)

**Interfaces:**
- Consumes: la sección per-role existente (`source`, `parameters` candidate fields).
- Produces: una subsección "Which keys each source consumes" que A3 puede citar.

- [ ] **Step 1:** Tras la tabla de candidate fields de la sección per-role (después de la descripción del campo `parameters`, ~línea 200), insertar:

```markdown
#### Which keys each source consumes (astromesh core v0.36.0+)

`parameters` and `timeout` are honored by **all** wired sources — until v0.36.0
several branches accepted them in the schema and then silently dropped them, so
a `temperature` or `timeout` set in YAML could have no effect. That is fixed:

| Key | `ollama` | `openai_compat` | `litellm` |
|-----|----------|-----------------|-----------|
| `parameters.temperature` / `top_p` / `max_tokens` | ✅ (routed into ollama's nested `options`; `max_tokens`→`num_predict`) | ✅ | ✅ |
| `parameters.presence_penalty` / `frequency_penalty` | ⚠️ warns — not on ollama's native surface | ✅ | ✅ |
| `timeout` | ✅ | ✅ (fixed v0.35.1) | ✅ |
| `endpoint` | ✅ | ✅ | ⚠️ ignored — litellm routes on the model prefix |

A model block that declares a key its source ignores now logs a `WARNING`
naming the source and the key, instead of dropping it in silence. Declare only
what the chosen source consumes.
```

- [ ] **Step 2 (verificación):**

Run: `grep -nE "Which keys each source consumes|num_predict|routes on the model prefix" schemas/astromesh-v1-agent.md`
Expected: las tres cadenas aparecen.

- [ ] **Step 3: Commit**

```bash
git add schemas/astromesh-v1-agent.md
git commit -m "docs(schema): matriz de keys consumidas por source en el model block (core v0.36.0)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task A3: Guía del architect para `client` tools

**Files:**
- Modify: `agents/leia-architect.md` (sección de tools/guía de generación)

**Interfaces:**
- Consumes: A1 (`Type: client`), A2 (keys por source).

- [ ] **Step 1 (verificación previa):** ubicar dónde el architect habla de tools.

Run: `grep -nE "tool|builtin|agent tool|internal" agents/leia-architect.md | head`
Expected: identifica la sección donde documenta la generación de `spec.tools`.

- [ ] **Step 2:** En esa sección, añadir un párrafo de guía (adaptar el fraseo al estilo del archivo):

```markdown
**Tool types.** Only `builtin`, `agent`, and `client` load from an agent YAML —
never emit `internal`, `mcp_*`, `webhook`, or `rag` as a tool `type`; the runtime
skips them with a WARNING and the agent ships with a tool nobody can call. Offer
a **`client`** tool when the value is the call itself and no Python-side action
exists (show a chart, open a form, hand off to the UI): the runtime announces it
to the model and returns `{"ok": true}`, and the arguments reach the live
consumer through the streaming `tool_call` event. If a capability genuinely needs
server-side execution, that is a `builtin` runtime tool or a delegated `agent`
tool, not a `client` one.
```

- [ ] **Step 3 (verificación):**

Run: `grep -nE "Only .builtin., .agent., and .client.|the call itself" agents/leia-architect.md`
Expected: coincide.

- [ ] **Step 4: Commit**

```bash
git add agents/leia-architect.md
git commit -m "docs(architect): guiar client tools y no emitir tipos no cargables

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task A4: Contrato de streaming + `usage.by_model` en los schemas

**Files:**
- Modify: `schemas/astromesh-v1-agent.md` (nueva sección al final, antes de cualquier apéndice) o `schemas/orchestration-patterns.md` — elegir el que hoy describe ejecución/observabilidad. Preferir `astromesh-v1-agent.md` con una sección nueva `## Streaming & usage`.

**Interfaces:**
- Consumes: A1 (client tools se entregan por este canal).

- [ ] **Step 1:** Añadir al final de `schemas/astromesh-v1-agent.md` la sección:

```markdown
---

## Streaming contract & usage (astromesh core v0.34.0 / v0.36.0)

A run is observable while it happens. `AgentRuntime.run()` accepts an `on_event`
callback and `/v1/ws/agent/{name}` streams the same events over WebSocket:

```
status → (token | tool_call | tool_result)* → done | error
```

- `token` — one whole model completion (per-iteration reasoning under ReAct; NOT the final answer).
- `tool_call` — `{id, name, arguments}`, emitted **before** the tool runs. For a `client` tool this event *is* the delivery.
- `tool_result` — `{id, ok}`, after the tool returns. A `client` tool always reports `ok: true`.
- `done` — `{answer, session_id, usage}`.

### usage.by_model (v0.36.0)

`done.usage` and the `/run` response carry per-model attribution — a single run
routinely touches several models (multi-model patterns, per-role routing,
provider fallback), so the flat `usage.model` has no correct value there.

```
usage = {
  tokens_in, tokens_out,            # totals (flat, kept for compatibility)
  model,                            # first model seen — legacy
  by_model: [ { provider, model, role, calls, tokens_in, tokens_out, cost } ]
}
```

`by_model` is the authoritative breakdown; sort is by descending consumption.
There is no cost/credits economics here beyond the provider `cost` estimate —
tenant billing lives in the nexus hub, not the core run response.
```

- [ ] **Step 2 (verificación):**

Run: `grep -nE "Streaming contract|usage.by_model|by_model:" schemas/astromesh-v1-agent.md`
Expected: las tres aparecen.

- [ ] **Step 3: Commit**

```bash
git add schemas/astromesh-v1-agent.md
git commit -m "docs(schema): contrato de streaming y usage.by_model (core v0.34.0/v0.36.0)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task A5: RAGPipeline CRUD + workflows/register en `nexus-api.md`

**Files:**
- Modify: `schemas/nexus-api.md` (añadir dos subsecciones de endpoints)

- [ ] **Step 1 (verificación previa):** ver el estilo de documentación de endpoints existente.

Run: `grep -nE "^## |^### |POST |GET " schemas/nexus-api.md | head -30`
Expected: patrón de secciones por endpoint identificado (para imitar formato).

- [ ] **Step 2:** Añadir, imitando el formato existente del archivo, dos subsecciones:

```markdown
### RAGPipeline resources (astromesh core v0.31.0+)

CRUD over RAGPipeline resources, the RAG twin of `/v1/agents`. An external tool
can author knowledge bases declaratively.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/rag/pipelines` | List pipelines (store seeded from `config/rag/*.rag.yaml`). |
| GET | `/v1/rag/pipelines/{name}` | Get one. |
| POST | `/v1/rag/pipelines` | Create; body validated via `RAGPipelineLoader.spec_from_raw` (422 on malformed). |
| PUT | `/v1/rag/pipelines/{name}` | Update; `metadata.name` must equal the path (400 otherwise). |
| DELETE | `/v1/rag/pipelines/{name}` | Delete. |

Distinct from the operation endpoints `/v1/rag/ingest` and `/v1/rag/query`.

### Dynamic blueprint registration (astromesh core v0.32.0+)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/workflows/register` | Register a full blueprint `{workflow, agents, rag_pipelines}` at runtime (RAG → agents → workflow order, so an agent's KB resolves at build). Idempotent upsert; 422 on invalid spec, 503 without engine/runtime. Launch it afterwards with the existing `POST /v1/workflows/{name}/run`. |
```

- [ ] **Step 3 (verificación):**

Run: `grep -nE "/v1/rag/pipelines|/v1/workflows/register|spec_from_raw" schemas/nexus-api.md`
Expected: coinciden.

- [ ] **Step 4: Commit**

```bash
git add schemas/nexus-api.md
git commit -m "docs(nexus-api): RAGPipeline CRUD y workflows/register (core v0.31/v0.32)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task A6: README — arreglar tabla de compatibilidad y link stale

**Files:**
- Modify: `README.md` (tabla "Version Compatibility" ~línea 119-124; link de descarga ~línea 56)

- [ ] **Step 1 (verificación previa):**

Run: `grep -nE "0.2.0.tar.gz|0.28.9|Version Compatibility|0.18" README.md`
Expected: muestra la fila stale (0.2.x / 0.18–0.28.9) y el link `astromesh-leia-v0.2.0.tar.gz`.

- [ ] **Step 2:** Añadir una fila a la tabla de compatibilidad para la versión nueva:

```markdown
| 0.4.x | 0.4.x | 0.29 – 0.36.x |
```

y actualizar el link de descarga stale de `astromesh-leia-v0.2.0.tar.gz` a `astromesh-leia-v0.4.0.tar.gz`.

- [ ] **Step 3 (verificación):**

Run: `grep -nE "0.4.x .* 0.29 . 0.36|v0.4.0.tar.gz" README.md`
Expected: coinciden; ya no hay referencia a `v0.2.0.tar.gz`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): compat 0.4.x ↔ core 0.29–0.36 y link de descarga

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task A7: Code review + CHANGELOG + release v0.4.0

**Files:**
- Modify: `CHANGELOG.md` (nueva sección `## [0.4.0]`), `.claude-plugin/plugin.json:3`, `README.md` (badge)

- [ ] **Step 1:** Ejecutar el skill `superpowers:requesting-code-review` sobre el diff de `develop` (Tasks A1–A6). Resolver Critical/Major antes de release.

- [ ] **Step 2:** Correr el workflow `validate` del repo si existe localmente; si no, validar manualmente que `.claude-plugin/plugin.json` sigue siendo JSON válido y que ningún template en `templates/` usa un tool `type` no cargable.

Run: `python -c "import json,sys; json.load(open('.claude-plugin/plugin.json'))" && grep -rlnE "type:\s*(internal|webhook|rag|mcp)" templates/ || echo "OK: sin tipos no cargables en templates"`
Expected: JSON válido y "OK".

- [ ] **Step 3:** Escribir la sección de CHANGELOG `## [0.4.0] - 2026-07-27` describiendo: corrección de tipos de tool cargables + `type: client`, matriz de keys por source, streaming + `usage.by_model`, RAGPipeline CRUD + workflows/register, README/compat. (Seguir el estilo Keep a Changelog del archivo.)

- [ ] **Step 4:** Bump de versión a `0.4.0` en `.claude-plugin/plugin.json:3` (`"version": "0.4.0"`) y en el badge del README (`version-0.4.0-green` + link `releases/tag/v0.4.0`).

- [ ] **Step 5 (verificación):**

Run: `grep -c '"version": "0.4.0"' .claude-plugin/plugin.json && grep -c "0.4.0" README.md && grep -c "0.4.0" CHANGELOG.md`
Expected: cada uno ≥ 1.

- [ ] **Step 6: Commit release**

```bash
git add CHANGELOG.md .claude-plugin/plugin.json README.md
git commit -m "chore(release): astromesh-leia 0.4.0

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 7: Merge a main + tag (SOLO tras confirmación del usuario y CI verde).**

```bash
git checkout main && git merge --no-ff develop -m "release: v0.4.0 — sync a core v0.36.0" && git tag -a v0.4.0 -m "astromesh-leia v0.4.0" && git checkout develop
```
Push (`git push origin develop main --tags`) SOLO cuando el usuario lo autorice; luego verificar el workflow `release` en verde.

---

# Track B — Cortex (`astromesh-cortex`) → v0.17.0

Repo: `/Users/fulfaro/monaccode/astromesh-cortex`. Branch: `develop`. Gate: `vitest` (~243 tests) + `tsc` + lint. TDD estricto.

### Task B1: `by_model` en el contrato `RunUsage` + validación

**Files:**
- Modify: `src/services/agent-run-events.ts:12-16` (RunUsage), `:56-64` (isRunUsage)
- Test: `src/services/__tests__/agent-run-events.test.ts` (crear si no existe; si existe, agregar casos)

**Interfaces:**
- Produces: `RunModelUsage { provider, model, role, calls, tokens_in, tokens_out, cost }` y `RunUsage.by_model?: RunModelUsage[] | null`. Consumido por B2 (api.ts) y B3 (AgentConsole).

- [ ] **Step 1: Test que falla.** Añadir a `src/services/__tests__/agent-run-events.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { parseRunEvent } from '../agent-run-events'

describe('parseRunEvent done.usage.by_model', () => {
  it('narrows by_model rows when present', () => {
    const ev = parseRunEvent({
      type: 'done',
      answer: 'ok',
      usage: {
        tokens_in: 10,
        tokens_out: 5,
        model: 'llama3',
        by_model: [
          { provider: 'ollama', model: 'llama3', role: 'default', calls: 1, tokens_in: 10, tokens_out: 5, cost: 0 },
        ],
      },
    })
    expect(ev?.type).toBe('done')
    if (ev?.type === 'done') {
      expect(ev.usage?.by_model?.[0].provider).toBe('ollama')
    }
  })

  it('accepts usage without by_model (pre-v0.36 runtime)', () => {
    const ev = parseRunEvent({ type: 'done', answer: 'ok', usage: { tokens_in: 1, tokens_out: 1, model: 'm' } })
    expect(ev?.type).toBe('done')
    if (ev?.type === 'done') expect(ev.usage?.by_model ?? null).toBeNull()
  })

  it('drops a malformed by_model row rather than the whole usage', () => {
    const ev = parseRunEvent({ type: 'done', answer: 'ok', usage: { tokens_in: 1, tokens_out: 1, model: 'm', by_model: [{ provider: 1 }] } })
    expect(ev?.type).toBe('done')
    if (ev?.type === 'done') expect(ev.usage?.by_model ?? []).toEqual([])
  })
})
```

- [ ] **Step 2: Correr y ver fallar.**

Run: `npx vitest run src/services/__tests__/agent-run-events.test.ts`
Expected: FAIL (by_model no existe en el tipo / no se valida).

- [ ] **Step 3: Implementar.** Reemplazar `RunUsage` (líneas 12-16) por:

```ts
export interface RunModelUsage {
  provider: string
  model: string
  role: string
  calls: number
  tokens_in: number
  tokens_out: number
  cost: number
}

export interface RunUsage {
  tokens_in: number
  tokens_out: number
  model: string
  /** Per-model attribution (astromesh core v0.36.0+). Absent on older runtimes. */
  by_model?: RunModelUsage[] | null
}
```

Añadir un guard y extender `isRunUsage` (líneas 56-64):

```ts
function isRunModelUsage(v: unknown): v is RunModelUsage {
  if (typeof v !== 'object' || v === null) return false
  const u = v as Record<string, unknown>
  return (
    typeof u.provider === 'string' &&
    typeof u.model === 'string' &&
    typeof u.role === 'string' &&
    typeof u.calls === 'number' &&
    typeof u.tokens_in === 'number' &&
    typeof u.tokens_out === 'number' &&
    typeof u.cost === 'number'
  )
}

function isRunUsage(v: unknown): v is RunUsage {
  if (typeof v !== 'object' || v === null) return false
  const u = v as Record<string, unknown>
  if (
    typeof u.tokens_in !== 'number' ||
    typeof u.tokens_out !== 'number' ||
    typeof u.model !== 'string'
  ) {
    return false
  }
  if (u.by_model != null) {
    if (!Array.isArray(u.by_model)) return false
    // Keep only well-formed rows; a bad row must not sink the whole usage.
    u.by_model = u.by_model.filter(isRunModelUsage)
  }
  return true
}
```

- [ ] **Step 4: Correr y ver pasar.**

Run: `npx vitest run src/services/__tests__/agent-run-events.test.ts`
Expected: PASS (3 casos).

- [ ] **Step 5: Commit**

```bash
git add src/services/agent-run-events.ts src/services/__tests__/agent-run-events.test.ts
git commit -m "feat(runtime): by_model en el contrato de usage del run (core v0.36.0)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task B2: Reflejar `by_model` en la forma HTTP de `usage`

**Files:**
- Modify: `src/types/api.ts:128`

- [ ] **Step 1 (verificación previa):**

Run: `grep -n "tokens_in: number; tokens_out: number; model: string" src/types/api.ts`
Expected: línea ~128.

- [ ] **Step 2:** Importar `RunModelUsage` y extender la forma inline de `usage`. Reemplazar:

```ts
  usage: { tokens_in: number; tokens_out: number; model: string } | null
```

por:

```ts
  usage: {
    tokens_in: number
    tokens_out: number
    model: string
    by_model?: import('../services/agent-run-events').RunModelUsage[] | null
  } | null
```

- [ ] **Step 3: Verificar tipos.**

Run: `npx tsc --noEmit`
Expected: sin errores nuevos.

- [ ] **Step 4: Commit**

```bash
git add src/types/api.ts
git commit -m "feat(types): by_model en la forma HTTP de usage (core v0.36.0)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task B3: Desglose por modelo en `AgentConsole` (estilo UsoPanel)

**Files:**
- Create: `src/components/console/RunUsageBreakdown.tsx`
- Modify: `src/components/console/AgentConsole.tsx` (donde se lee `msg.usage`, ~línea 132/244)
- Test: `src/components/console/__tests__/RunUsageBreakdown.test.tsx`

**Interfaces:**
- Consumes: `RunUsage` / `RunModelUsage` (B1).
- Produces: `<RunUsageBreakdown usage={usage} />` — renderiza la tabla si `by_model` tiene filas; si no, no renderiza nada.

- [ ] **Step 1 (verificación previa):** ver cómo el `UsoPanel` renderiza el desglose por modelo, para imitar el lenguaje visual.

Run: `grep -nE "models|provider|role|calls|tokens" src/shells/nexus/panels/UsoPanel.tsx | head -20`
Expected: identifica el markup de la tabla `models` (InvocationView) a imitar.

- [ ] **Step 2: Test que falla.** Crear `src/components/console/__tests__/RunUsageBreakdown.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { RunUsageBreakdown } from '../RunUsageBreakdown'

describe('RunUsageBreakdown', () => {
  it('renders a row per model when by_model is present', () => {
    const { getByText } = render(
      <RunUsageBreakdown
        usage={{
          tokens_in: 10,
          tokens_out: 5,
          model: 'llama3',
          by_model: [
            { provider: 'ollama', model: 'llama3', role: 'default', calls: 2, tokens_in: 10, tokens_out: 5, cost: 0.01 },
          ],
        }}
      />,
    )
    expect(getByText('llama3')).toBeTruthy()
    expect(getByText('ollama')).toBeTruthy()
  })

  it('renders nothing when by_model is empty or absent', () => {
    const { container } = render(
      <RunUsageBreakdown usage={{ tokens_in: 1, tokens_out: 1, model: 'm' }} />,
    )
    expect(container.firstChild).toBeNull()
  })
})
```

- [ ] **Step 3: Correr y ver fallar.**

Run: `npx vitest run src/components/console/__tests__/RunUsageBreakdown.test.tsx`
Expected: FAIL (módulo no existe).

- [ ] **Step 4: Implementar** `src/components/console/RunUsageBreakdown.tsx`. Usar los tokens de estilo del repo (mirroreando `UsoPanel`); estructura base:

```tsx
import type { RunUsage } from '../../services/agent-run-events'

export function RunUsageBreakdown({ usage }: { usage: RunUsage | null | undefined }) {
  const rows = usage?.by_model ?? []
  if (rows.length === 0) return null
  return (
    <table style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ color: 'rgba(255,255,255,0.5)', textAlign: 'left' }}>
          <th>Provider</th><th>Model</th><th>Role</th><th>Calls</th><th>In</th><th>Out</th><th>Cost</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((m, i) => (
          <tr key={`${m.provider}:${m.model}:${m.role}:${i}`}>
            <td>{m.provider}</td>
            <td>{m.model}</td>
            <td>{m.role}</td>
            <td>{m.calls}</td>
            <td>{m.tokens_in}</td>
            <td>{m.tokens_out}</td>
            <td>{m.cost ? `$${m.cost.toFixed(4)}` : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
```
(Ajustar clases/estilos para que matcheen el `UsoPanel`; conservar la firma y el early-return.)

- [ ] **Step 5: Correr y ver pasar.**

Run: `npx vitest run src/components/console/__tests__/RunUsageBreakdown.test.tsx`
Expected: PASS.

- [ ] **Step 6:** Montar `<RunUsageBreakdown usage={msg.usage} />` en `AgentConsole.tsx`, junto al render de tokens (`msg.usage.tokens_in`/`tokens_out`), colapsado bajo el total (ej. dentro de un `<details>` "Por modelo").

- [ ] **Step 7: Correr toda la suite + tipos + lint.**

Run: `npx vitest run && npx tsc --noEmit && npm run lint`
Expected: verde (suite completa, sin regresiones).

- [ ] **Step 8: Commit**

```bash
git add src/components/console/RunUsageBreakdown.tsx src/components/console/__tests__/RunUsageBreakdown.test.tsx src/components/console/AgentConsole.tsx
git commit -m "feat(console): desglose usage.by_model en corridas directas (core v0.36.0)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task B4: Actualizar referencias de versión del core + comentario del contrato

**Files:**
- Modify: `README.md:96` (ecosystem table `v0.35.1 → v0.36.0`), `src/services/agent-run-events.ts:1-2` (doc comment)

- [ ] **Step 1:** En `README.md`, actualizar la fila `Core Runtime (astromesh) | ... | v0.35.1` a `v0.36.0`. En el doc-comment de `agent-run-events.ts` (línea 2), añadir la mención de `usage.by_model` (core v0.36.0) sin borrar la referencia v0.34.0 del contrato de eventos.

- [ ] **Step 2 (verificación):**

Run: `grep -n "v0.36.0" README.md src/services/agent-run-events.ts`
Expected: coincide en ambos.

- [ ] **Step 3: Commit**

```bash
git add README.md src/services/agent-run-events.ts
git commit -m "docs: alinear referencias del core a v0.36.0

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task B5: Code review + CHANGELOG + release v0.17.0

**Files:**
- Modify: `CHANGELOG.md` (`[Unreleased]` → `## [0.17.0] - 2026-07-27`), `package.json:3`

- [ ] **Step 1:** Ejecutar `superpowers:requesting-code-review` sobre el diff de `develop` (B1–B4). Resolver Critical/Major.

- [ ] **Step 2:** Gate completo.

Run: `npx vitest run && npx tsc --noEmit && npm run lint`
Expected: verde.

- [ ] **Step 3:** Poblar `[Unreleased]` → `## [0.17.0] - 2026-07-27` con las entradas (Added: desglose `usage.by_model` en corridas directas; Changed: contrato `RunUsage` con `by_model`, refs del core a v0.36.0).

- [ ] **Step 4:** Bump `package.json` `"version": "0.17.0"`.

- [ ] **Step 5 (verificación):**

Run: `grep -c '"version": "0.17.0"' package.json && grep -c "0.17.0" CHANGELOG.md`
Expected: ambos ≥ 1.

- [ ] **Step 6: Commit release**

```bash
git add CHANGELOG.md package.json
git commit -m "chore(release): astromesh-cortex 0.17.0

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 7: Merge a main + tag (SOLO tras confirmación + CI verde).**

```bash
git checkout main && git merge --no-ff develop -m "release: v0.17.0 — usage.by_model en corridas directas" && git tag -a v0.17.0 -m "astromesh-cortex v0.17.0" && git checkout develop
```
Push SOLO cuando el usuario autorice; verificar CI.

---

# Track C — CLI (`astromesh/astromesh-cli`) → v0.2.0

Repo: monorepo `astromesh`, sub-paquete `astromesh-cli`. Branch: `develop`. Gate: `uv run pytest astromesh-cli/`. El release del CLI es un **commit** en `develop` (sin tag propio). TDD.

### Task C1: Bump del pin del core a v0.36.0

**Files:**
- Modify: `astromesh-cli/pyproject.toml:12`

- [ ] **Step 1:** Cambiar `"astromesh>=0.18.0",` por `"astromesh>=0.36.0",`. El path source editable (`[tool.uv.sources]`) no cambia.

- [ ] **Step 2 (verificación):**

Run: `grep -n "astromesh>=0.36.0" astromesh-cli/pyproject.toml`
Expected: coincide; ya no existe `>=0.18.0`.

- [ ] **Step 3: Commit**

```bash
git add astromesh-cli/pyproject.toml
git commit -m "chore(cli): pin astromesh core >=0.36.0

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task C2: `run` lee `usage` real y renderiza `by_model` (con fallback)

**Files:**
- Modify: `astromesh-cli/astromesh_cli/commands/run.py:51-62`
- Test: `astromesh-cli/tests/test_run_usage.py` (crear)

**Interfaces:**
- Consumes: la respuesta de `/v1/agents/{name}/run` = `{answer, steps, usage}` con `usage` = `UsageInfo` (Global Constraints). El código actual lee `response`/`tokens_used` (campos que la respuesta v0.36 no tiene) → hacer defensivo.

- [ ] **Step 1 (verificación previa del contrato real):** Confirmar la forma que devuelve el endpoint que el CLI golpea.

Run: `grep -n "class AgentRunResponse\|usage: UsageInfo\|by_model" ../astromesh/api/routes/agents.py`
(desde el root del monorepo: `astromesh/api/routes/agents.py`)
Expected: `AgentRunResponse{answer, steps, usage}`, `usage: UsageInfo | None`, `by_model: list[ModelUsage]`. Confirma que `run.py` debe leer `answer`/`usage`, no `response`/`tokens_used`.

- [ ] **Step 2: Test que falla.** Crear `astromesh-cli/tests/test_run_usage.py`:

```python
from astromesh_cli.commands.run import _format_run_output


def test_reads_answer_and_usage_totals():
    data = {
        "answer": "hola",
        "steps": [],
        "usage": {"tokens_in": 10, "tokens_out": 5, "model": "llama3", "by_model": []},
    }
    text, subtitle, rows = _format_run_output(data)
    assert text == "hola"
    assert "15" in subtitle or ("10" in subtitle and "5" in subtitle)
    assert rows == []


def test_builds_by_model_rows():
    data = {
        "answer": "hola",
        "usage": {
            "tokens_in": 10,
            "tokens_out": 5,
            "model": "llama3",
            "by_model": [
                {"provider": "ollama", "model": "llama3", "role": "default",
                 "calls": 2, "tokens_in": 10, "tokens_out": 5, "cost": 0.0},
            ],
        },
    }
    _text, _subtitle, rows = _format_run_output(data)
    assert rows[0]["provider"] == "ollama"
    assert rows[0]["model"] == "llama3"


def test_falls_back_to_legacy_fields():
    # Pre-v0.36 / daemon that returns response+tokens_used and no usage object.
    data = {"response": "hola", "tokens_used": 42}
    text, subtitle, rows = _format_run_output(data)
    assert text == "hola"
    assert "42" in subtitle
    assert rows == []
```

- [ ] **Step 3: Correr y ver fallar.**

Run: `uv run pytest astromesh-cli/tests/test_run_usage.py -v`
Expected: FAIL (`_format_run_output` no existe).

- [ ] **Step 4: Implementar.** Extraer un helper puro y usarlo en `run_command`. Reemplazar el bloque de render (líneas 51-62) por:

```python
    text, subtitle, by_model_rows = _format_run_output(data)
    console.print(
        Panel(
            text,
            title=f"[cyan]{name}[/cyan]",
            subtitle=subtitle,
            border_style="blue",
        )
    )
    if by_model_rows:
        table = Table(title="Por modelo", show_header=True)
        for col in ("Provider", "Model", "Role", "Calls", "In", "Out", "Cost"):
            table.add_column(col, style="cyan" if col == "Provider" else None)
        for r in by_model_rows:
            cost = r.get("cost", 0.0) or 0.0
            table.add_row(
                r.get("provider", ""), r.get("model", ""), r.get("role", ""),
                str(r.get("calls", 0)), str(r.get("tokens_in", 0)), str(r.get("tokens_out", 0)),
                f"${cost:.4f}" if cost else "—",
            )
        console.print(table)
```

y añadir el helper puro al módulo:

```python
def _format_run_output(data: dict) -> tuple[str, str, list[dict]]:
    """Extrae (texto, subtítulo, filas by_model) de la respuesta de /run.

    Prefiere el contrato del core v0.36.0 (answer + usage{tokens_in, tokens_out,
    by_model}); cae a los campos legacy (response + tokens_used) si no está.
    """
    text = data.get("answer") or data.get("response", "")
    trace_id = data.get("trace_id", "N/A")
    usage = data.get("usage")
    if isinstance(usage, dict):
        tin = usage.get("tokens_in", 0)
        tout = usage.get("tokens_out", 0)
        tokens = tin + tout
        by_model = usage.get("by_model") or []
    else:
        tokens = data.get("tokens_used", "N/A")
        by_model = []
    rows = [m for m in by_model if isinstance(m, dict)]
    subtitle = f"trace: {trace_id} | tokens: {tokens}"
    return text, subtitle, rows
```

- [ ] **Step 5: Correr y ver pasar.**

Run: `uv run pytest astromesh-cli/tests/test_run_usage.py -v`
Expected: PASS (3 casos).

- [ ] **Step 6: Lint.**

Run: `uv run ruff check astromesh-cli/`
Expected: limpio.

- [ ] **Step 7: Commit**

```bash
git add astromesh-cli/astromesh_cli/commands/run.py astromesh-cli/tests/test_run_usage.py
git commit -m "feat(cli): run lee usage real y muestra by_model (core v0.36.0)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task C3: `version` reporta también el core instalado

**Files:**
- Modify: `astromesh-cli/astromesh_cli/main.py:49-52`
- Test: `astromesh-cli/tests/test_version.py` (crear)

- [ ] **Step 1 (verificación previa):**

Run: `sed -n '48,53p' astromesh-cli/astromesh_cli/main.py`
Expected: el comando `version` imprime `astromesh {__version__}` (la del CLI).

- [ ] **Step 2: Test que falla.** Crear `astromesh-cli/tests/test_version.py`:

```python
from typer.testing import CliRunner
from astromesh_cli.main import app

runner = CliRunner()


def test_version_reports_cli_and_core():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "cli" in result.stdout.lower()
    assert "core" in result.stdout.lower()
```

- [ ] **Step 3: Correr y ver fallar.**

Run: `uv run pytest astromesh-cli/tests/test_version.py -v`
Expected: FAIL (no dice "core").

- [ ] **Step 4: Implementar.** En `main.py`, reemplazar el cuerpo de `version` por:

```python
    from importlib.metadata import PackageNotFoundError, version as _pkg_version

    typer.echo(f"astromesh-cli {__version__}")
    try:
        typer.echo(f"astromesh core {_pkg_version('astromesh')}")
    except PackageNotFoundError:
        typer.echo("astromesh core (not installed)")
```

- [ ] **Step 5: Correr y ver pasar.**

Run: `uv run pytest astromesh-cli/tests/test_version.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add astromesh-cli/astromesh_cli/main.py astromesh-cli/tests/test_version.py
git commit -m "feat(cli): version reporta también el core astromesh instalado

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task C4: Crear CHANGELOG + code review + release v0.2.0

**Files:**
- Create: `astromesh-cli/CHANGELOG.md`
- Modify: `astromesh-cli/pyproject.toml:7`, `astromesh-cli/astromesh_cli/__init__.py:3`

- [ ] **Step 1:** Ejecutar `superpowers:requesting-code-review` sobre el diff del sub-paquete (C1–C3). Resolver Critical/Major.

- [ ] **Step 2:** Gate completo del sub-paquete.

Run: `uv run pytest astromesh-cli/ && uv run ruff check astromesh-cli/`
Expected: verde.

- [ ] **Step 3:** Crear `astromesh-cli/CHANGELOG.md` (Keep a Changelog) con `## [0.2.0] - 2026-07-27`: Added (`version` reporta el core; render `usage.by_model` en `run`), Changed (pin `astromesh>=0.36.0`; `run` lee el contrato `usage` del core con fallback legacy).

- [ ] **Step 4:** Bump `0.1.1 → 0.2.0` en `astromesh-cli/pyproject.toml:7` y `astromesh-cli/astromesh_cli/__init__.py:3`.

- [ ] **Step 5 (verificación):**

Run: `grep -c '0.2.0' astromesh-cli/pyproject.toml astromesh-cli/astromesh_cli/__init__.py astromesh-cli/CHANGELOG.md`
Expected: cada archivo ≥ 1.

- [ ] **Step 6: Commit release**

```bash
git add astromesh-cli/CHANGELOG.md astromesh-cli/pyproject.toml astromesh-cli/astromesh_cli/__init__.py
git commit -m "chore(release): astromesh-cli 0.2.0

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 7:** El CLI es sub-paquete del monorepo → **sin tag propio**. Los commits quedan en `develop`; se integran a `main` en el flujo normal del repo `astromesh`. Push de `develop` SOLO cuando el usuario lo autorice; verificar CI del repo core.

---

## Self-Review (contra el spec)

**Spec coverage:**
- LEIA tool types + `client` → A1 ✅ · model key matrix → A2 ✅ · architect guidance → A3 ✅ · streaming + usage.by_model → A4 ✅ · RAGPipeline CRUD + workflows/register → A5 ✅ · README/compat → A6 ✅ · release v0.4.0 → A7 ✅
- Cortex by_model tipo/validación → B1 ✅ · api.ts → B2 ✅ · display estilo UsoPanel → B3 ✅ · version refs → B4 ✅ · release v0.17.0 → B5 ✅
- CLI pin → C1 ✅ · run by_model → C2 ✅ · version core → C3 ✅ · CHANGELOG + release v0.2.0 → C4 ✅

**Placeholder scan:** Sin "TBD/TODO". Los pasos de UI (B3) que imitan el `UsoPanel` incluyen código concreto y firma; el ajuste de estilos es cosmético sobre una base funcional dada. Los pasos de contenido markdown (LEIA) incluyen el texto verbatim a escribir.

**Type consistency:** `RunModelUsage`/`RunUsage.by_model` (B1) se consumen con el mismo nombre en B2 y B3. `_format_run_output` (C2) → `(text, subtitle, rows)` consistente entre test e implementación. `ModelUsage` del core (Global Constraints) coincide campo a campo con `RunModelUsage` (Cortex) y las filas del CLI.

**Riesgo residual anotado:** el contrato real del endpoint que golpea el CLI se re-verifica en C2 Step 1 antes de editar; el fallback legacy hace el cambio seguro aunque el daemon envuelva distinto.
