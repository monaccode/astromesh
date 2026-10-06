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
    timeout_seconds: 60             # Hard timeout for the entire agent execution

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

    semantic:                       # Vector-based memory for similarity search
      backend: chromadb             # Vector store (pgvector, chromadb, qdrant, faiss)
      similarity_threshold: 0.75   # Minimum cosine similarity to return a result
      max_results: 5                # Maximum number of similar items to retrieve

  # --- Guardrails ---
  guardrails:
    input:                          # Applied to user messages before the LLM call
      - type: pii_detection
        action: redact              # redact = mask PII, block = reject the message
      - type: max_length
        max_chars: 5000

    output:                         # Applied to agent responses after the LLM call
      - type: cost_limit
        max_tokens_per_turn: 1000
      - type: pii_detection
        action: redact
      - type: content_filter
        forbidden_keywords: ["internal", "confidential"]
      - type: topic_filter
        forbidden_topics: ["politics", "religion"]

  # --- Permissions ---
  permissions:
    allowed_actions:                # Restricts which tools this agent can invoke
      - lookup_company
      - search_crm
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

Only the `react` and `glyph` patterns separate it from the system prompt. Every other pattern gets it appended to the end of the system prompt, and the agent logs a warning at load time. Do not iterate `memory.conversation` inside `prompts.context`: the history already travels as messages.

The agent also warns at load time when `prompts.system` uses `knowledge`, `prefetch` or `memory.semantic`/`episodic` inside Jinja blocks (`{{ }}` / `{% %}`), since that changes the prefix on every query and defeats the cache. Move it to `prompts.context`.

### `spec.orchestration`

| Field | Required | Description |
|-------|----------|-------------|
| `pattern` | Yes | The orchestration pattern. See the patterns table below. |
| `max_iterations` | No | Maximum number of reasoning iterations. Prevents infinite loops. Default: `10`. |
| `timeout_seconds` | No | Hard timeout in seconds for the entire agent execution. When exceeded, the agent returns whatever partial result it has. |

### `spec.tools`

Each tool is an object in the `tools` array:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Tool name. Must be unique within the agent. |
| `type` | Yes | Tool type loadable from YAML: `builtin` (a tool shipped with the runtime), `agent` (another agent, callable as a tool), `client` (announced to the model, executed by whoever is listening), `integration` (catalog actions), `api` or `mcp` (a tenant's API or MCP server, declared inline). `mcp_stdio`/`mcp_sse`/`mcp_http`, `webhook` and `rag` exist in the runtime's `ToolType` but are not declarable from an agent YAML file. |
| `description` | Yes | Description of what the tool does. Sent to the LLM for function calling. |
| `parameters` | No | JSON Schema-like parameter definitions. Each parameter has a `type` and `description`. |

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
| `semantic.backend` | No | Vector store: `pgvector`, `chromadb`, `qdrant`, `faiss`. |
| `semantic.similarity_threshold` | No | Minimum cosine similarity score (0.0-1.0) for results. |
| `semantic.max_results` | No | Maximum number of similar items to retrieve. |

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

### `spec.guardrails`

Each guardrail is an object in the `input` or `output` array:

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Guardrail type. See the guardrail types table below. |
| `action` | Depends | For `pii_detection`: `redact` (mask the PII) or `block` (reject the message). |
| `max_chars` | Depends | For `max_length`: maximum character count. |
| `max_tokens_per_turn` | Depends | For `cost_limit`: maximum tokens in a single response. |
| `forbidden_keywords` | Depends | For `content_filter`: list of keywords that trigger blocking. |
| `forbidden_topics` | Depends | For `topic_filter`: list of topics that trigger blocking. |

### `spec.permissions`

| Field | Required | Description |
|-------|----------|-------------|
| `allowed_actions` | No | List of tool names this agent is permitted to invoke. If omitted, the agent can use all tools defined in its `tools` section. |

## Orchestration Patterns

| Pattern | Value | Best For |
|---------|-------|----------|
| ReAct | `react` | General-purpose agents that need to reason and use tools iteratively. Default pattern. |
| Plan and Execute | `plan_and_execute` | Complex multi-step tasks where upfront planning improves results. |
| Parallel Fan-Out | `parallel_fan_out` | Tasks that benefit from multiple parallel perspectives, merged into a single answer. |
| Pipeline | `pipeline` | Sequential processing chains where each step transforms the output. |
| Supervisor | `supervisor` | Task delegation to specialized sub-agents managed by a coordinator. |
| Swarm | `swarm` | Multi-agent conversations where agents hand off to each other based on context. |

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

| Type | Direction | Description |
|------|-----------|-------------|
| `pii_detection` | input, output | Detects and redacts emails, phone numbers, SSNs, and credit card numbers. |
| `max_length` | input | Rejects messages exceeding the configured `max_chars` limit. |
| `cost_limit` | output | Truncates responses that exceed `max_tokens_per_turn`. |
| `content_filter` | output | Blocks responses containing any of the `forbidden_keywords`. |
| `topic_filter` | output | Blocks responses matching any of the `forbidden_topics`. |

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
