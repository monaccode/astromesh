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
      type: internal                # Tool type (internal, mcp, webhook, rag)
      description: "Look up company information from CRM"
      parameters:
        company_name:
          type: string
          description: "Company name to look up"

    - name: search_crm
      type: webhook
      description: "Search CRM records"
      parameters:
        query:
          type: string
          description: "Search query"

  # --- Memory ---
  memory:
    conversational:
      backend: redis                # Storage backend (redis, postgres, sqlite)
      strategy: sliding_window      # How conversation history is managed
      max_turns: 20                 # For sliding_window: number of turns to retain
      ttl: 3600                     # Time-to-live in seconds (redis and sqlite)

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
| `fallback` | No | Fallback provider configuration. Same fields as `primary`. Used when the primary provider fails or the circuit breaker opens. |
| `routing.strategy` | No | Routing strategy for provider selection. Default: `cost_optimized`. |
| `routing.health_check_interval` | No | Seconds between health checks. Default: `30`. |

### `spec.prompts`

| Field | Required | Description |
|-------|----------|-------------|
| `system` | Yes | The system prompt sent to the LLM. Supports Jinja2 template syntax for variable injection (e.g., `{{ user_name }}`). Use a YAML literal block (`\|`) for multi-line prompts. |
| `templates` | No | Named Jinja2 templates that can be referenced from tools or orchestration steps. Keys are template names, values are template strings. |

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
| `type` | Yes | Tool type: `internal` (Python function), `mcp` (Model Context Protocol server), `webhook` (HTTP endpoint), `rag` (RAG pipeline as tool). |
| `description` | Yes | Description of what the tool does. Sent to the LLM for function calling. |
| `parameters` | No | JSON Schema-like parameter definitions. Each parameter has a `type` and `description`. |

### `spec.memory`

| Field | Required | Description |
|-------|----------|-------------|
| `conversational.backend` | No | Storage backend: `redis`, `postgres`, `sqlite`. |
| `conversational.strategy` | No | History management strategy. See the strategies table below. |
| `conversational.max_turns` | No | Number of conversation turns to retain (for `sliding_window`). |
| `conversational.ttl` | No | Time-to-live in seconds. Conversations expire after this duration. |
| `semantic.backend` | No | Vector store: `pgvector`, `chromadb`, `qdrant`, `faiss`. |
| `semantic.similarity_threshold` | No | Minimum cosine similarity score (0.0-1.0) for results. |
| `semantic.max_results` | No | Maximum number of similar items to retrieve. |

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
| Sliding Window | `sliding_window` | Simple conversations where only recent context matters. Keeps the last N turns. |
| Summary | `summary` | Long-running conversations that need full history. Older turns are compressed into summaries. |
| Token Budget | `token_budget` | You need precise control over context window usage. Fits as many turns as possible within a token limit. |

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
