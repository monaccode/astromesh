---
title: Your First Agent
description: Create and run a custom agent from scratch
---

This guide walks you through creating a custom Astromesh agent from scratch. You will start with a minimal YAML definition, test it, and then progressively add a fallback model, memory, tools, and guardrails.

## Create the Agent YAML

Create a new file at `config/agents/hello.agent.yaml`:

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: hello-agent
  version: "1.0.0"
  namespace: demo

spec:
  identity:
    display_name: "Hello Agent"
    description: "A simple greeting agent for learning the basics"

  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"
      endpoint: "http://localhost:11434"
      parameters:
        temperature: 0.7
        max_tokens: 1024

  prompts:
    system: |
      You are a friendly assistant named Astro. You greet users warmly,
      answer questions concisely, and always sign off with a fun space fact.

      Keep responses under 3 sentences unless the user asks for detail.

  orchestration:
    pattern: react
    max_iterations: 5
    timeout_seconds: 30
```

If the daemon is already running, restart it to pick up the new agent:

```bash
uv run astromeshd --config ./config --log-level debug
```

Check that the agent was loaded:

```bash
curl http://localhost:8000/v1/agents
```

## Call the Agent

```bash
curl -X POST http://localhost:8000/v1/agents/hello-agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Hi there! What can you do?",
    "session_id": "test-001"
  }'
```

Expected response:

```json
{
  "answer": "Hey there! I'm Astro, your friendly assistant. I can answer questions, chat, and share fun space facts. Did you know that a day on Venus is longer than a year on Venus?",
  "steps": [],
  "usage": { "tokens_in": 142, "tokens_out": 45, "model": "llama3.1:8b", "by_model": [ ... ] },
  "blocked": false,
  "guardrail": null
}
```

`answer` is the reply, `steps` the orchestration steps (empty when the model answered without tools), and `usage` the tokens summed from the run's trace. The full response also carries `trace`, `data`, `chain` and `propuestas`; see [API Endpoints](/astromesh/reference/api-endpoints/). Your agent is running. Now let's understand what each part of the YAML does and then build on it.

## Understanding the YAML

### `apiVersion` and `kind`

```yaml
apiVersion: astromesh/v1
kind: Agent
```

Every Astromesh resource starts with these two fields. `apiVersion` is always `astromesh/v1` for the current release. `kind` is `Agent` for agent definitions. This follows the Kubernetes-style resource model — other kinds (like `RAGPipeline`) use the same pattern.

### `metadata`

```yaml
metadata:
  name: hello-agent
  version: "1.0.0"
  namespace: demo
```

- **`name`** — the unique identifier for this agent. This is used in API routes (`/v1/agents/hello-agent/run`) and must be unique across all loaded agents.
- **`version`** — semantic version for tracking changes to the agent definition.
- **`namespace`** — logical grouping. Useful for organizing agents by team or domain.

### `spec.identity`

```yaml
spec:
  identity:
    display_name: "Hello Agent"
    description: "A simple greeting agent for learning the basics"
```

Human-readable metadata. The `display_name` appears in logs and the management API. The `description` is used for agent discovery and documentation.

### `spec.model.primary`

```yaml
spec:
  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"
      endpoint: "http://localhost:11434"
      parameters:
        temperature: 0.7
        max_tokens: 1024
```

- **`provider`** — which LLM backend to use. Options: `ollama`, `openai`, `vllm`, `llamacpp`, `huggingface`, `onnx`.
- **`model`** — the model identifier, specific to the provider. For Ollama this is the tag name; for OpenAI this is the model ID (e.g., `gpt-4o`).
- **`endpoint`** — the provider's API URL. Required for self-hosted providers; omitted for cloud providers like OpenAI that use well-known endpoints.
- **`parameters.temperature`** — controls randomness. Lower values (0.1-0.3) for factual tasks, higher (0.7-1.0) for creative tasks.
- **`parameters.max_tokens`** — maximum tokens in the generated response.

### `spec.prompts.system`

```yaml
spec:
  prompts:
    system: |
      You are a friendly assistant named Astro. ...
```

The system prompt defines the agent's personality and behavior. This is a Jinja2 template — you can use variables like `{{ agent_name }}` and `{{ description }}` that the Prompt Engine injects at runtime. The user's query and the conversation history are sent as messages, not rendered into the prompt.

### `spec.orchestration`

```yaml
spec:
  orchestration:
    pattern: react
    max_iterations: 5
    timeout_seconds: 30
```

- **`pattern`** — the reasoning strategy. `react` (Reason-Act loop) is the most common. Other options: `plan_and_execute`, `parallel_fan_out`, `pipeline`, `supervisor`, `swarm`.
- **`max_iterations`** — safety cap on reasoning loops. The agent will stop after this many iterations even if it hasn't reached a final answer.
- **`timeout_seconds`** — hard timeout for the entire orchestration run.

## Add a Fallback Model

What happens when your primary provider goes down? Add a fallback so the agent automatically fails over.

Add the `fallback` section under `spec.model`:

```yaml
spec:
  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"
      endpoint: "http://localhost:11434"
      parameters:
        temperature: 0.7
        max_tokens: 1024
    fallback:
      provider: openai
      model: "gpt-4o-mini"
      parameters:
        temperature: 0.7
        max_tokens: 1024
    routing:
      strategy: quality_first
```

Now if Ollama fails (network error, timeout, or 3 consecutive failures triggering the circuit breaker), the Model Router automatically routes to OpenAI. The `routing.strategy` controls how the primary is selected when both are healthy:

- `quality_first` — always use primary unless it is down
- `cost_optimized` — pick the cheapest provider
- `latency_optimized` — pick the fastest provider
- `round_robin` — alternate between providers

For the fallback to work with OpenAI, set the `OPENAI_API_KEY` environment variable before starting the daemon.

## Add Memory

Without memory, each request to the agent is stateless — it has no recall of previous messages. Add conversational memory so the agent maintains context within a session.

Add the `memory` section to `spec`:

```yaml
spec:
  memory:
    conversational:
      backend: redis
      strategy: sliding_window
      max_turns: 20
      connection:
        url: "redis://localhost:6379/0"
```

Restart the daemon and test with multiple messages in the same session:

```bash
# First message
curl -X POST http://localhost:8000/v1/agents/hello-agent/run \
  -H "Content-Type: application/json" \
  -d '{"query": "My name is Jordan.", "session_id": "mem-test"}'
```

```json
{
  "answer": "Nice to meet you, Jordan! I'm Astro, happy to chat with you. Fun fact: the footprints on the Moon will last for millions of years since there's no wind to blow them away!",
  "steps": [],
  "usage": { ... },
  "blocked": false,
  "guardrail": null
}
```

```bash
# Second message — same session_id
curl -X POST http://localhost:8000/v1/agents/hello-agent/run \
  -H "Content-Type: application/json" \
  -d '{"query": "What is my name?", "session_id": "mem-test"}'
```

```json
{
  "answer": "Your name is Jordan! Great to still be chatting with you. Here's a space fact: Saturn's density is so low it would float in water if you could find a bathtub big enough!",
  "steps": [],
  "usage": { ... },
  "blocked": false,
  "guardrail": null
}
```

The agent remembers your name because the Memory Manager persisted the first exchange to Redis and injected it as context in the second request.

Memory strategies control how the history is managed as it grows:

- **`sliding_window`** — keeps the last N turns and drops older ones.
- **`summary`** — folds turns that leave the window into a running summary.
- **`token_budget`** — keeps as many turns as fit the model's context window (set `context_window` on the model).

If you don't have Redis running, you can use `sqlite` as the backend for local development:

```yaml
spec:
  memory:
    conversational:
      backend: sqlite
      strategy: sliding_window
      max_turns: 20
```

## Add a Tool

Tools let agents take actions beyond generating text. Let's add the built-in `datetime_now` tool, which returns the current date and time in a given timezone.

Add the `tools` section to `spec`:

```yaml
spec:
  tools:
    - name: datetime_now
      type: builtin
```

Update the system prompt to tell the agent about tool usage:

```yaml
spec:
  prompts:
    system: |
      You are a friendly assistant named Astro. You greet users warmly,
      answer questions concisely, and always sign off with a fun space fact.

      You have access to tools. When a user asks about the current time or date,
      use the datetime_now tool to provide an accurate answer.

      Keep responses under 3 sentences unless the user asks for detail.
```

Restart the daemon and test:

```bash
curl -X POST http://localhost:8000/v1/agents/hello-agent/run \
  -H "Content-Type: application/json" \
  -d '{"query": "What time is it right now?", "session_id": "tool-test"}'
```

Expected response:

```json
{
  "answer": "It's currently 2026-03-09T14:23:45Z. Fun fact: because of the speed of light, when you look at the Sun, you're actually seeing it as it was about 8 minutes ago!",
  "steps": [ ... ],
  "usage": { ... },
  "blocked": false,
  "guardrail": null
}
```

`steps` now records the tool call: the ReAct pattern used one iteration to decide to call the tool, and a second to formulate the answer with the tool's output.

## Add Guardrails

Guardrails protect both the user and the system. Let's redact PII in the user's message, filter some words from the answer, and cap the tokens a run can spend.

Add the `guardrails` section to `spec`:

```yaml
spec:
  guardrails:
    input:
      - type: pii_detection
        action: redact
    output:
      - type: content_filter
        action: block
        forbidden_keywords: ["internal-only"]
        message: "I can't share that."
      - type: cost_limit
        max_tokens_per_turn: 4000
```

Now if a user includes PII in their message, it is redacted before reaching the LLM (the email below becomes `[REDACTED_EMAIL]`):

```bash
curl -X POST http://localhost:8000/v1/agents/hello-agent/run \
  -H "Content-Type: application/json" \
  -d '{"query": "My email is jordan@example.com, can you remember it?", "session_id": "guard-test"}'
```

The response has the usual shape. A redaction does not show up in it; the model just never sees the address. A rule that blocks (for example the `content_filter` above, or the `cost_limit` once the run has spent its budget) returns a normal `200` response with the rule's message and which rule fired:

```json
{
  "answer": "I can't share that.",
  "steps": [],
  "blocked": true,
  "guardrail": { "direction": "output", "rule": "content_filter", "reason": "pattern matched" }
}
```

`cost_limit` is a budget of output tokens for the whole run, tool loops included, so keep it around 4000; values like 500 would cut runs that use tools. The full list of rules, actions and defaults is in the [Agent YAML Schema](/astromesh/configuration/agent-yaml/#specguardrails).

## The Complete Agent

Here is the full `config/agents/hello.agent.yaml` with all the additions from this guide:

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: hello-agent
  version: "1.0.0"
  namespace: demo

spec:
  identity:
    display_name: "Hello Agent"
    description: "A friendly greeting agent with memory, tools, and guardrails"

  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"
      endpoint: "http://localhost:11434"
      parameters:
        temperature: 0.7
        max_tokens: 1024
    fallback:
      provider: openai
      model: "gpt-4o-mini"
      parameters:
        temperature: 0.7
        max_tokens: 1024
    routing:
      strategy: quality_first

  prompts:
    system: |
      You are a friendly assistant named Astro. You greet users warmly,
      answer questions concisely, and always sign off with a fun space fact.

      You have access to tools. When a user asks about the current time or date,
      use the datetime_now tool to provide an accurate answer.

      Keep responses under 3 sentences unless the user asks for detail.

  orchestration:
    pattern: react
    max_iterations: 5
    timeout_seconds: 30

  tools:
    - name: datetime_now
      type: builtin

  memory:
    conversational:
      backend: redis
      strategy: sliding_window
      max_turns: 20
      connection:
        url: "redis://localhost:6379/0"

  guardrails:
    input:
      - type: pii_detection
        action: redact
    output:
      - type: content_filter
        action: block
        forbidden_keywords: ["internal-only"]
        message: "I can't share that."
      - type: cost_limit
        max_tokens_per_turn: 4000
```

You started with a 30-line minimal agent and built up to a production-ready definition with provider failover, session memory, tool usage, and safety guardrails — all in YAML, no application code.

## Next Steps

Dive deeper into the configuration options in the [Agent YAML Schema](/astromesh/configuration/agent-yaml/) reference, or explore the available [Orchestration Patterns](/astromesh/architecture/agent-pipeline/) to understand when to use each reasoning strategy.
