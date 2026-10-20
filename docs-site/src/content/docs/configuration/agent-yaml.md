---
title: Agent YAML Schema
description: Complete reference for agent configuration files
---

Agents are the primary resource in Astromesh. Each agent is defined in a YAML file that specifies its model, prompts, orchestration pattern, tools, memory, guardrails, and permissions. The runtime loads all agent definitions at startup and makes them available through the API.

## File Location

Agent configuration files live in `config/agents/` (development) or `/etc/astromesh/agents/` (production). Files must follow the naming convention `<name>.agent.yaml`.

Every agent file uses the standard Astromesh header:

```yaml
apiVersion: astromesh/v1
kind: Agent
```

## Minimal Agent

The smallest valid agent definition requires a name, a model, and a system prompt:

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: my-agent
  version: "1.0.0"

spec:
  identity:
    display_name: "My Agent"
    description: "A simple assistant"

  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"
      endpoint: "http://ollama:11434"
      parameters:
        temperature: 0.7
        max_tokens: 2048

  prompts:
    system: |
      You are a helpful assistant.

  orchestration:
    pattern: react
    max_iterations: 10
```

This agent uses a local Ollama instance, the ReAct orchestration pattern, and no tools, memory, or guardrails. Everything beyond this minimal definition is optional.

## Full Agent Reference

Below is a complete agent definition with every available field documented:

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: sales-qualifier        # Unique identifier — used in API routes (/v1/agents/sales-qualifier/run)
  version: "1.0.0"             # Semantic version for tracking changes
  namespace: sales              # Logical grouping (informational, not enforced)
  labels:                       # Arbitrary key-value pairs for filtering and organization
    team: revenue
    tier: production

spec:
  # --- Identity ---
  identity:
    display_name: "Sales Lead Qualifier"    # Human-readable name shown in UIs
    description: "Qualifies incoming sales leads using BANT methodology"
    avatar: "sales-bot"                     # Optional avatar identifier

  # --- Skills (optional) ---
  # What the agent can do. Published as skills in its A2A Agent Card.
  skills:
    - id: qualify-lead
      name: "Qualify lead"
      description: "Scores a lead with BANT and recommends a next step"
      tags: [sales, bant]
      examples: ["Qualify this lead: ACME, 200 seats, budget approved"]
      inputModes: [text/plain]
      outputModes: [application/json]

  # --- Model Selection ---
  model:
    primary:
      provider: ollama              # Provider type (must match a key in providers.yaml)
      model: "llama3.1:8b"         # Model name or path
      endpoint: "http://ollama:11434"
      api_key_env: ""               # Environment variable name for API key (if required)
      parameters:
        temperature: 0.3            # 0.0 = deterministic, 1.0 = creative
        top_p: 0.9                  # Nucleus sampling threshold
        max_tokens: 2048            # Maximum response length in tokens

    fallback:                       # Used when the primary provider fails or is unavailable
      provider: openai_compat
      model: "gpt-4o-mini"
      endpoint: "https://api.openai.com/v1"
      api_key_env: OPENAI_API_KEY   # References os.environ["OPENAI_API_KEY"]
      parameters:
        temperature: 0.3
        max_tokens: 2048

    routing:
      strategy: cost_optimized      # How the model router selects a provider
      health_check_interval: 30     # Seconds between provider health checks

  # --- System Prompt ---
  prompts:
    system: |                       # Jinja2 template — variables are injected at runtime
      You are a sales lead qualification assistant using BANT methodology.

      For each lead, assess:
      - **Budget**: Can they afford the solution?
      - **Authority**: Are they the decision maker?
      - **Need**: Do they have a genuine need?
      - **Timeline**: When do they plan to purchase?

      Provide a qualification score (1-10) and recommended next action.

    templates:                      # Named Jinja2 templates for reuse
      greeting: "Hello {{ user_name }}, how can I help you today?"

  # --- Orchestration Pattern ---
  orchestration:
    pattern: react                  # Reasoning and execution pattern
    max_iterations: 5               # Maximum reasoning loop iterations before stopping
    timeout_seconds: 120            # Cuts the run when exceeded (HTTP 504); keep it >= 120

  # --- Tools ---
  tools:
    - name: lookup_company
      type: builtin                 # builtin | agent | client | integration | api | mcp
      description: "Look up company information from CRM"
      parameters:
        company_name:
          type: string
          description: "Company name to look up"

    - name: google_sheets           # an integration slug: one entry, several tools
      type: integration
      connection: sheets_main       # which connection carries the credential
      actions:                      # allowlist — required
        - get_values
        - append_values
      confirm:                      # subset of actions that need a human "yes"
        - append_values
```

> **Tool types loadable from YAML:** `builtin` (a tool shipped with the runtime),
> `agent` (another agent, callable as a tool), `client` (announced to the model,
> executed by whoever is listening — the call arrives live via `on_event` and
> afterwards in `steps`; with nobody listening it is a no-op), and `integration`
> (actions from a catalog manifest — see [Integrations](/astromesh/configuration/integrations/)).
> `api` and `mcp` (since v0.57.0 / v0.58.0) are a tenant's own API or MCP server declared
> inline — see [Tenant APIs & MCP Servers](/astromesh/configuration/tenant-apis-and-mcp/).
> Unlike the other types, an invalid `api` or `mcp` entry **does not load the agent**.
>
> `webhook` and `rag` appear in `ToolType` but are **not** declarable from YAML.
> `internal` is deprecated: a YAML cannot supply a Python handler, so what it meant
> is now `client`. Declaring an unsupported type logs a warning and skips the tool;
> from 1.0 it will be an error.
>
> A key this runtime does not read is **warned about, not ignored in silence** (since
> v0.43.0): the log names the agent, the tool and the ignored keys. That usually means the
> manifest was written for a newer runtime than the one running it.

```yaml
  # --- Memory ---
  memory:
    conversational:
      backend: redis                # redis is the only backend the runtime builds
      connection:
        url: redis://localhost:6379/0   # required — no default
      strategy: sliding_window      # How conversation history is managed
      max_turns: 20                 # Turns read from the store (and kept verbatim)
      ttl: 3600                     # Time-to-live in seconds (default: 259200 — 72h)

    semantic:                       # Optional; embeddings are required (see spec.memory below)
      backend: faiss
      dimension: 768
      embeddings: {provider: ollama, model: nomic-embed-text}
    episodic:                       # Optional; one event per run
      backend: postgres
      connection: {url: postgresql://user:pass@localhost:5432/astromesh}

  # --- Guardrails ---
  guardrails:
    input:                          # Applied to user messages before memory and the model
      - type: pii_detection
        action: redact              # redact (default) | block | warn
      - type: max_length
        max_chars: 5000             # truncates by default

    output:                         # Applied to the final answer and to streamed tokens
      - type: pii_detection
        action: redact
      - type: content_filter
        forbidden_keywords: ["internal", "confidential"]
      - type: cost_limit            # run-wide output-token budget
        max_tokens_per_turn: 4000

  # --- Permissions ---
  permissions:
    allowed_actions:                # Whitelist of registered tool names (fnmatch wildcards)
      - lookup_company
      - search_crm
    denied_actions: []              # Blacklist; wins over allowed_actions
```

## Per-role Models

Beyond a single `primary`/`fallback` pair, an agent can declare a distinct model — or list of candidate models — for each orchestration role. This lets you pair a cheap local model for routine tool loops with a frontier cloud model for planning, all within one agent:

```yaml
spec:
  model:
    default:
      candidates:
        - {source: ollama, model: "llama3.1:8b", endpoint: "http://localhost:11434"}
      strategy: cost_optimized
    roles:
      planner:
        candidates:
          - {source: litellm, model: "anthropic/claude-opus-4-8", api_key_env: ANTHROPIC_API_KEY}
        strategy: quality_first
      worker:
        candidates:
          - {source: ollama, model: "llama3.1:8b"}
        strategy: cost_optimized

  orchestration:
    pattern: plan_and_execute
    max_iterations: 6
```

`default` is required whenever this schema is used — it is the router every unrecognized or unconfigured role falls back to. `roles` is a map from role name to its own candidate list and strategy; each role becomes its own independent `ModelRouter`, with its own circuit breaker (see [Model Router](/astromesh/reference/core/model-router/#per-role-routers)). See `config/agents/role-router-demo.agent.yaml` for the complete worked example above.

### Candidate fields

Each entry in a `candidates` array is an object with:

| Field | Required | Description |
|-------|----------|-------------|
| `source` | No | Provider family: `litellm` (cloud multi-provider, see [Providers](/astromesh/configuration/providers/#litellm-source-cloud-multi-provider)), `ollama`, or `openai_compat` (aliases `openai`, `azure_openai`). If omitted, it is inferred from `model`: a name containing `/` (e.g. `anthropic/claude-opus-4-8`) infers `litellm`; otherwise it infers `openai_compat`. |
| `model` | Yes | Model name or path. Format depends on `source` (e.g. `"llama3.1:8b"` for Ollama, `"anthropic/claude-opus-4-8"` for LiteLLM). |
| `endpoint` | No | Override endpoint URL. Defaults vary by `source` (e.g. `http://localhost:11434` for Ollama). |
| `api_key_env` | No | Name of the environment variable containing the API key. |
| `api_key` | No | Inline API key. Prefer `api_key_env` so secrets stay out of YAML. |
| `parameters` | No | Sampling parameters (`temperature`, `top_p`, `max_tokens`, etc.), passed through to the provider. |
| `context_window` | No | The model's context window in tokens. Sizes the conversation-history budget (see [Memory Strategies](#memory-strategies)). Without it the runtime falls back to `parameters.num_ctx` (Ollama), then to what litellm knows. |

A role (or `default`) can list multiple `candidates`; its `ModelRouter` selects and falls back between them according to its `strategy`, exactly like the legacy `primary`/`fallback` pair.

### Role vocabulary

Each orchestration pattern requests one or more named roles at its decision points. Any role your agent hasn't defined under `roles` falls back to `default`:

| Pattern | Roles requested |
|---------|------------------|
| ReAct | `reasoner` |
| Plan and Execute | `planner`, `worker`, `synthesizer` |
| Parallel Fan-Out | `planner`, `worker`, `synthesizer` |
| Pipeline | `stage:<name>` for each configured stage (default stages: `analyze`, `process`, `synthesize`) |
| Supervisor | `supervisor` |
| Swarm | `reasoner` |

### Remapping roles with `orchestration.role_map`

`role_map` points a pattern's built-in role request at one of your own role names, without renaming the role in your agent's `roles` map:

```yaml
spec:
  orchestration:
    pattern: react
    role_map:
      reasoner: planner   # ReAct's "reasoner" requests route to the "planner" role's router
```

Resolution order for a requested role: `role_map[role]` (if the role is remapped) → the resolved name looked up in `spec.model.roles` → `default` if no router is registered under the resolved name.

### Backward compatibility

The legacy `primary` / `fallback` / `extra` / `routing.strategy` shape shown in [Full Agent Reference](#full-agent-reference) still works unchanged. Internally it is normalized into a single `default` role — there is no need to migrate existing agents. Adopt `default`/`roles` only where you want per-role model selection.

## Field Reference

### `metadata`

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier. Used in API routes (`/v1/agents/{name}/run`) and channel configuration. Must be lowercase with hyphens. |
| `version` | Yes | Semantic version string (e.g., `"1.0.0"`). For tracking changes; not enforced at runtime. |
| `namespace` | No | Logical grouping for organizing agents. Informational only. |
| `labels` | No | Arbitrary key-value pairs. Useful for filtering, categorization, and operational metadata. |

### `spec.identity`

| Field | Required | Description |
|-------|----------|-------------|
| `display_name` | Yes | Human-readable name shown in logs, UIs, and API responses. |
| `description` | Yes | Short description of what the agent does. |
| `avatar` | No | Avatar identifier for UI integrations. |

### `spec.skills`

Optional list of what the agent can do. Astromesh publishes it as the `skills` of the agent's A2A Agent Card, and `GET /v1/agents/{name}` returns it.

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Stable skill identifier. |
| `name` | Yes | Human-readable name. |
| `description` | Yes | What the skill does. |
| `tags` | No | List of keywords for discovery. |
| `examples` | No | List of example prompts. |
| `inputModes` | No | Accepted MIME types (camelCase, as in A2A). |
| `outputModes` | No | Produced MIME types. |

An invalid skill (missing `id`, `name` or `description`, or wrong types) is skipped with a warning; the agent still loads.

### `spec.a2a`

Read by [Astromesh Nexus](/astromesh/nexus/a2a-server/) only; the core runtime ignores it.

| Field | Required | Description |
|-------|----------|-------------|
| `publicar` | No | `true` publishes the agent over A2A 1.0 in Nexus: an Agent Card (with `spec.identity.description` and `spec.skills`) and a JSON-RPC endpoint behind the tenant's credentials. Off by default. Read from the live version, so a new version without it unpublishes the agent. |

See [A2A](/astromesh/a2a/introduction/) for the whole picture.

### `spec.model`

| Field | Required | Description |
|-------|----------|-------------|
| `primary.provider` | Yes | Provider type. Must match a provider configured in `providers.yaml`. Values: `ollama`, `openai_compat`, `vllm`, `llamacpp`, `hf_tgi`, `onnx`. |
| `primary.model` | Yes | Model name or path. Format depends on the provider (e.g., `"llama3.1:8b"` for Ollama, `"gpt-4o"` for OpenAI). |
| `primary.endpoint` | Yes* | Provider endpoint URL. Not required for `onnx` (local inference). |
| `primary.api_key_env` | No | Name of the environment variable containing the API key. The runtime reads `os.environ[api_key_env]` at startup. |
| `primary.parameters.temperature` | No | Sampling temperature. `0.0` = deterministic, `1.0` = maximum randomness. Default varies by provider. |
| `primary.parameters.top_p` | No | Nucleus sampling threshold. Default: `0.9`. |
| `primary.parameters.max_tokens` | No | Maximum number of tokens in the response. |
| `primary.context_window` | No | The model's context window in tokens. Sizes the history budget (see [Memory Strategies](#memory-strategies)). Same field on `fallback`. |
| `fallback` | No | Fallback provider configuration. Same fields as `primary`. Used when the primary provider fails or the circuit breaker opens. |
| `routing.strategy` | No | Routing strategy for provider selection. Default: `cost_optimized`. |
| `routing.health_check_interval` | No | Seconds between health checks. Default: `30`. |

### `spec.prompts`

| Field | Required | Description |
|-------|----------|-------------|
| `system` | Yes | The system prompt sent to the LLM. Supports Jinja2 template syntax for variable injection (e.g., `{{ user_name }}`). Use a YAML literal block (`\|`) for multi-line prompts. |
| `templates` | No | Named Jinja2 templates that can be referenced from tools or orchestration steps. Keys are template names, values are template strings. |
| `context` | No | Jinja2 template for what changes on every query (RAG `knowledge`, `prefetch`). Rendered per run and put next to the user message instead of in the system prompt. See below. |

#### `prompts.context`

Anything that depends on the query belongs here, not in `prompts.system`. The runtime places it in front of the current user message, so the final prompt is ordered:

```
system → tools → history → [glyph grammar] → context + query
```

Everything before the last message is identical between calls, so the provider's automatic prompt cache (Kimi/Moonshot, OpenAI, vLLM) can serve it. The turn stored in memory is the original query, without the context.

```yaml
prompts:
  system: |
    You are Lucia, a sales analyst. Answer with the data I give you.
  context: |
    {% if knowledge %}RELEVANT DOCUMENTS:
    {{ knowledge }}{% endif %}
    {% if prefetch.stock %}CURRENT STOCK: {{ prefetch.stock }}{% endif %}
```

Every pattern except `swarm` puts it in front of the current user message, apart from the system prompt. `swarm` gets it appended to the end of the system prompt, and the agent logs a warning at load time. Do not iterate `memory.conversation` inside `prompts.context`: the history already travels as messages.

The agent also warns at load time when `prompts.system` uses `knowledge`, `prefetch` or `memory.semantic`/`episodic` inside Jinja blocks (`{{ }}` / `{% %}`), since that changes the prefix on every query and defeats the cache. Move it to `prompts.context`.

Prompt templates in a manifest (`prompts.system`, `prompts.context`, the `when` of `prefetch`) are rendered in a Jinja sandbox (since core 0.59.1), so a template cannot reach Python internals; the system prompt can carry text a tenant writes.

### `spec.orchestration`

| Field | Required | Description |
|-------|----------|-------------|
| `pattern` | Yes | The orchestration pattern. See the patterns table below. |
| `max_iterations` | No | Maximum number of reasoning iterations. Prevents infinite loops. Default: `10`. |
| `stages` | No | For `pipeline`: 2 to 6 stage names of 1 to 40 characters. Default: `analyze`, `process`, `synthesize`. Anything else fails at load time. |
| `timeout_seconds` | No | Hard timeout in seconds for the entire agent execution. When exceeded the run is cut: HTTP `504` `{"error": "timeout", "agent", "timeout_seconds"}` on `/v1/agents/{name}/run` and `POST /v1/workflows/{name}/run`, and an `error` event with `error: "timeout"` on the WebSocket. An in-flight tool is closed with a `tool_result` `{ok: false, cancelled: true}`, and a `timeout` episode is recorded if episodic memory is on. Must be a number > 0, otherwise the agent fails to load. `timeout` is a deprecated alias. The provider's own HTTP timeout is 120 s, so values under 120 cut runs with tools or slow models. |
| `max_handoffs` | No | For `swarm`: integer >= 1, default `3`. Caps chained handoffs; once reached, handoffs are no longer offered or executed. |
| `max_tool_result_tokens` | No | Default cap, in tokens, for each tool result that reaches the model. Overridden per tool by `max_result_tokens`. Default: `8000`. See [Tool result budget](#tool-result-budget). |

Pattern behavior (since core 0.65.0):

- An unknown `pattern` fails when the agent is built with `AgentConfigError` (it used to fall back to `react` silently). `pattern: null` means `react`.
- `plan_and_execute`, `parallel_fan_out` and `pipeline` are conversational: the planner or decomposer and the synthesizer get the history and the turn context; in `pipeline` only the first stage does.
- Every plan step, pipeline stage or subtask runs the same tool loop as `react` (without the history), so tool results go back to the model.
- A plan has at most 6 steps and a fan-out at most 4 subtasks. `parallel_fan_out` cancels the remaining subtasks when one fails.
- `supervisor` needs at least one `type: agent` tool, and offers the model only those tools.

### `spec.tools`

Each tool is an object in the `tools` array:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Tool name. Must be unique within the agent. |
| `type` | Yes | Tool type loadable from YAML: `builtin` (a tool shipped with the runtime), `agent` (another agent, callable as a tool), `client` (announced to the model, executed by whoever is listening), `integration` (catalog actions), `api` or `mcp` (a tenant's API or MCP server, declared inline), `a2a` (a remote A2A agent, core 0.74.0+ with the `astromesh[a2a]` extra; see [A2A tools](/astromesh/a2a/astromesh-tools/)). `mcp_stdio`/`mcp_sse`/`mcp_http`, `webhook` and `rag` exist in the runtime's `ToolType` but are not declarable from an agent YAML file. |
| `description` | Yes | Description of what the tool does. Sent to the LLM for function calling. |
| `parameters` | No | JSON Schema-like parameter definitions. Each parameter has a `type` and `description`. |
| `max_result_tokens` | No | Cap, in tokens, for this tool's result when it enters the conversation. For `integration`, `api` and `mcp` it applies to every tool that definition registers. Falls back to `orchestration.max_tool_result_tokens`, then to `8000`. |

#### Tool result budget

A tool can return far more than the model needs. Each result is capped when it enters the conversation, so one large response cannot fill the window. It applies to the patterns that share the tool loop: `react`, `plan_and_execute`, `pipeline`, `parallel_fan_out` and `supervisor`. `swarm` is covered too. Glyph programs receive the full data, uncapped.

- `dict` and `list` results reach the model as compact JSON, not as a Python `repr`.
- A list keeps its first elements and ends with `{"_omitidos": N, "_nota": "..."}`.
- A dict trims its largest list, even one nested inside other dicts (`data.results`), and keeps every other key.
- Anything else is cut at the head and ends with `[resultado recortado: X de Y tokens]`.

The limit comes from `tools[].max_result_tokens`, then `orchestration.max_tool_result_tokens`, then the runtime default of `8000`. A value that is not an integer greater than 0 logs a warning at load and falls back to the next level. Earlier observations are never rewritten, because that would change the cached prefix (see [Prompt Caching](/astromesh/advanced/prompt-caching/)). Trimmed results are reported in traces: see [Observability](/astromesh/advanced/observability/).

### `spec.prefetch`

Read-only lookups that run **before the model**, so a turn that always starts by looking up
the same thing does not spend an LLM round trip deciding to do it. Available since
astromesh **v0.51.0**.

```yaml
spec:
  tools:
    - name: praxis
      type: integration
      connection: praxis_main
      actions: [buscar_records]
  prefetch:
    - name: cliente
      tool: praxis_buscar_records          # the registered tool name, <slug>_<action>
      arguments:
        entidad: cliente
        filter: "telefono:eq:{{ sender_phone }}"
      when: "sender_phone is defined"      # optional; an expression, not a template
  prompts:
    system: |
      {% if prefetch is defined and prefetch.cliente.success %}
      Customer: {{ prefetch.cliente.data }}
      {% endif %}
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Key under `prefetch` in the prompt. Unique within the block. |
| `tool` | Yes | A registered integration action (catalog `integration`, or an `api` read operation) whose request method is `GET` and that is not in `confirm`. |
| `arguments` | No | Object. String values are Jinja2 templates rendered with the run context (the caller's keys such as `sender_phone`) and the results of earlier entries (`prefetch.<name>`). |
| `when` | No | Jinja2 **expression**, evaluated rather than rendered — a rendered `{{ rows }}` of an empty list is the string `"[]"`, which is not empty. False skips the entry. |

Entries run in order, after RAG and before the prompt is rendered, through
`ToolRegistry.execute` with the run's own credentials. Each result lands in
`prefetch.<name>` as `{success, data, metadata, error}`, and each call emits a
`tool.prefetch` span.

- **An invalid declaration does not load the agent** — an unregistered tool, a tool that is
  not an integration action, a non-`GET` action, an action in `confirm`, a repeated `name`,
  and (since **v0.51.1**) a `when` or an `arguments` template that does not compile. Unlike
  the rest of the spec, skipping it silently would leave the model without the data.
- **A lookup that fails at run time does not fail the turn.** The entry gets
  `success: false` and the model keeps its tools. A `when` that compiles but raises while
  evaluating degrades the same way.
- A prompt that reads `prefetch` and may run on an older runtime must guard with
  `prefetch is defined`: reading an attribute of an undefined variable is not silenced.

### `spec.memory`

| Field | Required | Description |
|-------|----------|-------------|
| `conversational.backend` | No | `redis`. See the caveat below. |
| `conversational.connection.url` | With `redis` | Redis URL. Read with no default — omit it and the agent runs **without memory**. |
| `conversational.strategy` | No | History management strategy. See the strategies table below. |
| `conversational.max_turns` | No | Number of turns read back per run. With `summary`, turns beyond it are folded into the summary. |
| `conversational.ttl` | No | Time-to-live in seconds. Default `259200` (72h). |

:::note[Semantic and episodic memory]
Both are built from the manifest (since core 0.71.0).

- `memory.semantic.backend`: `chromadb`, `faiss`, `pgvector` or `qdrant`. `embeddings` is **required** (`provider`: `ollama`, `hf` or `sentence_transformer`, plus `model`; same shape as a RAG pipeline's embedder), with no implicit default. `dimension` is required for `faiss`, `pgvector` and `qdrant`; `connection.url` for `pgvector` (optional for `qdrant`). Each backend needs its extra (`astromesh[chromadb]`, `[faiss]`, `[qdrant]`, `[postgres]`; `[embeddings]` for `sentence_transformer`).
- `memory.episodic.backend`: `postgres` only, with `connection.url` (extra `astromesh[postgres]`).
- A manifest that gets any of this wrong, or lacks the extra, stays in `draft` with an `AgentConfigError`. A backend that fails at run time is logged and the run continues without that memory.
- Semantic memory reaches the prompt as `memory.semantic` (`{content, similarity, source}`, no vector). Episodic memory writes **one episode per run** (result `ok`, `blocked`, `error` or `timeout`, tools called, tokens and the guardrail rule; when the input was blocked, or the run failed before the input guardrails ran, the query is not stored) and `memory.episodic` carries the 5 most recent episodes of the same session.
- Both are **scoped to the session**: semantic search and episodic recall filter by `session_id` in the backend query, so one person's answers never reach another person's prompt.
- A sub-agent (a `type: agent` tool or a swarm target) keeps its memory in its own session, `<session_id>::<agent name>`, and stores only the request it received, not the conversation transcript.
:::

:::caution[The schema announces more backends than the factory builds]
`agent.schema.json` accepts `redis`, `postgres`, `sqlite` and `in_memory` for
`conversational.backend`. The factory builds **only `redis`**. Declaring one of the other
three logs a warning naming the backend and the agent runs **without conversational
memory** — it will reintroduce itself on every message. The runtime degrades rather than
refusing to start: an agent killed by a memory dependency is a bigger failure than an
agent without memory, but the operator has to be able to see it in the pod log.

The same warning fires when the backend package is not installed in this build
(`pip install "astromesh[redis]"`), and when `connection.url` is missing.

Until **v0.44.0** none of this was visible: the `MemoryManager` was constructed without its
backend at all, so *no agent had conversational memory with any backend* and the
`memory_build` / `memory_persist` spans still reported `ok`.
:::

### `spec.knowledge`

| Field | Required | Description |
|-------|----------|-------------|
| `pipeline` | One of `pipeline`/`bundle` | `metadata.name` of a `RAGPipeline`. Retrieved chunks reach the templates as `knowledge`. |
| `top_k` | No | Chunks per run for `pipeline`. Defaults to the pipeline's `retrieval.top_k`. |
| `bundle` | One of `pipeline`/`bundle` | Directory of an [OKF knowledge bundle](/astromesh/advanced/knowledge-bundles/), relative to the config directory or absolute. Registers `kb_index`, `kb_read` and `kb_find`, and exposes `bundle_index` to the templates. |

```yaml
knowledge:
  pipeline: product-knowledge
  bundle: knowledge/acme_retail
```

### `spec.guardrails`

Each guardrail is an object in the `input` or `output` array. Rules run in declared order. A rule that blocks does not raise an error: the run returns normally with `blocked: true`, the rule's `message` as `answer`, and a `guardrail` object (see [API Endpoints](/astromesh/reference/api-endpoints/)). Rules the engine does not understand are discarded with a warning at load time; the agent still loads.

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Guardrail type. See the guardrail types table below. |
| `action` | No | What to do on a match. Valid actions and the default (first) depend on the type; see the table below. |
| `message` | No | Text returned as `answer` when the rule blocks. Default: `I can't help with that request.` |
| `max_chars` | No | For `max_length`: maximum character count (default `10000`). Alias: `max_characters`. |
| `max_tokens_per_turn` | Yes, for `cost_limit` | Output-token budget for the whole run. |
| `count` | No | For `cost_limit`: `output` (default) or `total` (input + output tokens). |
| `forbidden_keywords` | Depends | For `content_filter`: keywords matched case-insensitively. |
| `blocked_patterns` | Depends | For `content_filter`: case-insensitive regular expressions. |
| `blocked_topics` / `forbidden_topics` | Yes, for `topic_filter` | Topics matched case-insensitively as substrings. |

`blocked_categories` and `allowed_topics` need a classifier that does not exist; they are ignored with a warning at load time.


:::caution[Breaking since core 0.70.0]
Before 0.70.0 `spec.guardrails` was not enforced. Manifests that already declare guardrails change behavior: input `pii_detection` now redacts by default (the phone pattern matches any 10-digit number, so order IDs and card numbers stop reaching tools; move redaction to the output if tools need them), `max_length` truncates at 10000 characters by default, and `cost_limit.max_tokens_per_turn` is a real run-wide budget, so old values of 500-1500 cut runs that use tools (around 4000 is recommended). A block returns `blocked: true` instead of an error.
:::

:::caution[Breaking since core 0.71.0]
Sections that used to load with no effect now do something, so existing manifests can change:

- `orchestration.timeout_seconds` cuts the run (HTTP 504). Values of 30-90 s cut runs with tools or slow models; use 120 or more, or drop the key.
- `permissions.allowed_actions` / `denied_actions` are a whitelist / blacklist of registered tool names; a name that matches nothing leaves that tool out.
- `memory.semantic` without `embeddings` does not load; each backend needs its extra. `memory.episodic` (`postgres`) is also built.
- `pattern: swarm` without a `type: agent` tool does not load.
- `permissions.filesystem`, `network` and `execution`, and other keys, are ignored with a warning.
- `register_internal(...)` and `register_agent_tool(...)` with `permissions=` now raise `TypeError` (`ToolDefinition.permissions` was removed).
- These now fail to load with `AgentConfigError` (before, they loaded with no effect): an unknown `memory.semantic.backend` (including `in_memory`); a `memory.episodic.backend` other than `postgres` (for example `sqlite`); a missing `dimension` (`faiss`, `pgvector`, `qdrant`) or `connection.url` (`pgvector`, `postgres`); a `timeout_seconds` that is a string, `0`, negative or a bool; `permissions` that is not a mapping, or `allowed_actions` / `denied_actions` that are not lists; a `prefetch` naming a tool that `permissions` leaves out.
- `orchestration.timeout` (the deprecated alias) also cuts the run.
- Semantic and episodic memory are per session; a sub-agent's memory lives in `<session_id>::<agent name>`.
- Python API: `SwarmPattern(agent_configs)` becomes `SwarmPattern(workers, max_handoffs=3)`; `Agent(..., permissions=)` becomes `permitidas=`; `get_tool_schemas(agent_permissions)` becomes `get_tool_schemas(permitidas)` and filters by tool name; `SemanticBackend.search` and `EpisodicBackend.recall` take `session_id=`.
:::

### `spec.permissions`

| Field | Required | Description |
|-------|----------|-------------|
| `allowed_actions` | No | Whitelist of **registered** tool names, with `fnmatch` wildcards (`kb_*`). A tool that matches no pattern is neither offered to the model nor executable. Registered names are `<slug>_<action>` for `integration`, `api` and `mcp` tools and `kb_*` for knowledge bundles. |
| `denied_actions` | No | Blacklist with the same rules. It wins over `allowed_actions`. |

Both are applied when tools are offered and when they run. A pattern that matches nothing, or a result with no tools left, is logged as a warning; a `prefetch` that names a disallowed tool is an `AgentConfigError`. Any other key under `permissions` (`filesystem`, `network`, `execution`...) is ignored with a warning.

## Orchestration Patterns

| Pattern | Value | Best For |
|---------|-------|----------|
| ReAct | `react` | General-purpose agents that need to reason and use tools iteratively. Default pattern. |
| Plan and Execute | `plan_and_execute` | Complex multi-step tasks where upfront planning improves results. |
| Parallel Fan-Out | `parallel_fan_out` | Tasks that benefit from multiple parallel perspectives, merged into a single answer. |
| Pipeline | `pipeline` | Sequential processing chains where each step transforms the output. |
| Supervisor | `supervisor` | Task delegation to specialized sub-agents managed by a coordinator. Needs at least one `type: agent` tool: those are its workers. |
| Swarm | `swarm` | Hands control to a `type: agent` tool; the target's answer is the final answer. Needs at least one `type: agent` tool; `max_handoffs` caps chains (see [Multi-Agent](/astromesh/configuration/multi-agent/#swarm-pattern)). |

## Memory Strategies

| Strategy | Value | Use When |
|----------|-------|----------|
| Sliding Window | `sliding_window` | Simple conversations where only recent context matters. Keeps the last `max_turns` turns. |
| Summary | `summary` | Long-running conversations that need full history. Turns that fall out of the `max_turns` window are folded into a running summary. |
| Token Budget | `token_budget` | You need precise control over context window usage. Fits as many recent turns as the budget allows. |

Token counts are real: every turn is stored with its `token_count` (rows written by older versions are estimated on read). Whatever the strategy, the history is trimmed to a budget of 90% of the model's context window minus the system prompt, the tool schemas, the response `max_tokens` and the `prompts.context` text, newest turns first. History is sent to the model as messages.

The window comes from `context_window` on the model candidate, else `parameters.num_ctx` (Ollama), else litellm. With several candidates, the smallest wins. If it cannot be determined, history is **not** trimmed by budget, only by `max_turns`, and the agent warns at load time: declare `context_window` to turn the budget on.

```yaml
model:
  primary:
    provider: ollama
    model: llama3
    context_window: 8192
```

`summary` is incremental. Once `max_turns` is exceeded, after each assistant turn (one call per exchange, inline) the turns that just left the verbatim window are merged into the previous summary by the `summarizer` role, falling back to `default`. That adds one model call of latency to that run. A failed summary does not break the turn.

Putting `memory.conversation` in `prompts.system` still works and keeps the old behavior (the history is rendered into the system prompt, no messages are sent), but it changes the prompt on every turn and the agent warns at load time.

## Guardrail Types

| Type | Direction | Actions (default first) | Description |
|------|-----------|-------------------------|-------------|
| `pii_detection` | input, output | `redact`, `block`, `warn` | Detects emails, US-format phone numbers, SSNs and credit card numbers. |
| `topic_filter` | input | `warn`, `block` | Matches `blocked_topics` (alias `forbidden_topics`) in the message. |
| `max_length` | input | `truncate`, `block` | Applies to messages longer than `max_chars` (alias `max_characters`, default 10000). |
| `content_filter` | output | `redact`, `block` | Matches `forbidden_keywords` or `blocked_patterns`; `redact` replaces matches with `[FILTERED]`. |
| `cost_limit` | run (accepted under `input` or `output`) | `block` | Output-token budget for the whole run (`count: total` includes input). Checked before each model call; once spent, the run ends with `guardrail.direction: run`. |

## Tips

### Use environment variables for secrets

Never hardcode API keys in agent YAML files. Use the `api_key_env` field to reference an environment variable by name:

```yaml
spec:
  model:
    primary:
      provider: openai_compat
      api_key_env: OPENAI_API_KEY   # Reads os.environ["OPENAI_API_KEY"]
```

### Naming conventions

- Agent names should be lowercase with hyphens: `support-agent`, `sales-qualifier`
- File names must match the pattern `<name>.agent.yaml`
- The `metadata.name` field must be unique across all agents — it is used in API routes

### Start minimal, add complexity

Begin with the minimal agent definition and add sections as you need them. You do not need tools, memory, or guardrails to get a working agent. Add each capability when your use case requires it.
