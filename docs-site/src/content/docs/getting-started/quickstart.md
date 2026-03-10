---
title: Quick Start
description: Get Astromesh running in 5 minutes
---

This guide takes you from zero to a running agent in five steps. By the end, you will have Astromesh running locally with an LLM provider and will have executed an agent query through the REST API.

## Step 1: Clone and Install

```bash
git clone https://github.com/monaccode/astromesh.git
cd astromesh
uv sync --extra all
```

Expected output (last few lines):

```
Resolved 127 packages in 3.42s
Installed 127 packages in 8.91s
```

## Step 2: Configure a Provider

Astromesh needs at least one LLM provider to run agents. Pick whichever option suits your setup.

### Option A: Ollama (local, no API key needed)

Start the Ollama server and pull a model:

```bash
ollama serve &
ollama pull llama3.1:8b
```

Expected output:

```
pulling manifest
pulling 8eeb52dfb3bb... 100% ▕████████████████▏ 4.7 GB
pulling 948af2743fc7... 100% ▕████████████████▏ 1.5 KB
pulling 0ba8f0e314b4... 100% ▕████████████████▏  12 KB
success
```

The default agent configuration in `config/agents/support-agent.agent.yaml` is already set up to use Ollama at `http://localhost:11434`, so no additional configuration is needed.

### Option B: OpenAI (cloud, requires API key)

Export your API key:

```bash
export OPENAI_API_KEY="sk-..."
```

Then update the support agent to use OpenAI by editing `config/agents/support-agent.agent.yaml`:

```yaml
spec:
  model:
    primary:
      provider: openai
      model: "gpt-4o-mini"
      parameters:
        temperature: 0.2
        max_tokens: 2048
```

## Step 3: Initialize the Project

Run the init wizard in development mode:

```bash
uv run astromeshctl init --dev
```

Expected output:

```
Astromesh Init (dev mode)
=========================
[+] Created config/runtime.yaml
[+] Created config/providers.yaml
[+] Created config/channels.yaml
[+] Detected Ollama at http://localhost:11434
[+] Found 3 agent definitions in config/agents/
[+] Initialization complete

Run 'astromeshd --config ./config' to start the daemon.
```

The `--dev` flag tells the init wizard to use the local `./config/` directory instead of `/etc/astromesh/`. It detects available providers, validates agent YAML files, and generates any missing configuration.

## Step 4: Start the Dev Server

Start the Astromesh development server with hot-reload:

```bash
uv run astromeshctl dev
```

Expected output:

```
╭─ astromesh dev ──────────────────────────────╮
│ Astromesh Dev Server                         │
│                                              │
│   Host:   0.0.0.0                            │
│   Port:   8000                               │
│   Config: ./config                           │
│   Reload: enabled                            │
╰──────────────────────────────────────────────╯
INFO:     Started server on http://0.0.0.0:8000
INFO:     Application startup complete
```

The dev server watches `astromesh/` and `config/` for changes and automatically restarts. Leave this terminal running.

:::tip
You can also start the daemon directly with `uv run astromeshd --config ./config --log-level debug` for production-style startup without hot-reload.
:::

## Step 5: Verify

Open a new terminal and hit the health endpoint:

```bash
curl http://localhost:8000/v1/health
```

Expected response:

```json
{
  "status": "healthy",
  "version": "0.10.0",
  "agents_loaded": 3,
  "uptime_seconds": 5.2
}
```

You should see `"status": "healthy"` and `"agents_loaded": 3` confirming all three bundled agents are ready.

## Step 6: Run an Agent

You can run agents using either the CLI or the REST API.

### Using the CLI

```bash
uv run astromeshctl run support-agent "What are your business hours?"
```

Expected output:

```
╭─ support-agent ──────────────────────────────────────────╮
│ Our business hours are Monday through Friday, 9:00 AM to │
│ 5:00 PM EST. We're closed on weekends and major holidays.│
╰── trace: abc-123 | tokens: 342 ─────────────────────────╯
```

### Using the REST API

```bash
curl -X POST http://localhost:8000/v1/agents/support-agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are your business hours?",
    "session_id": "demo-001"
  }'
```

Expected response:

```json
{
  "agent": "support-agent",
  "session_id": "demo-001",
  "response": "Our business hours are Monday through Friday, 9:00 AM to 5:00 PM EST. We're closed on weekends and major holidays. Is there anything else I can help you with?",
  "metadata": {
    "provider": "ollama",
    "model": "llama3.1:8b",
    "pattern": "plan_and_execute",
    "iterations": 2,
    "tokens_used": 342,
    "latency_ms": 1847
  }
}
```

The response includes the agent's reply along with metadata about which provider, model, and orchestration pattern were used, how many reasoning iterations it took, and the total latency.

## What Just Happened?

When you sent that request, the following pipeline executed inside Astromesh:

1. **API Layer** received the POST request and resolved the agent name `support-agent` to its loaded configuration.
2. **Input Guardrails** ran PII detection on the query. No PII was found, so the query passed through unchanged.
3. **Memory Manager** loaded conversational history for `session_id: demo-001`. This was the first message, so the history was empty.
4. **Prompt Engine** rendered the Jinja2 system prompt, injecting the conversation history and the user query.
5. **Orchestration (PlanAndExecute)** generated a plan to answer the question, then executed each step — in this case, a single LLM call was sufficient.
6. **Model Router** sent the request to the Ollama provider. The circuit breaker confirmed the provider was healthy.
7. **Output Guardrails** ran PII detection on the response and checked the token cost limit (342 tokens, under the 500-token cap).
8. **Memory Manager** persisted the exchange (query + response) to the conversational memory backend for future context.
9. **API Layer** returned the response with execution metadata.

All of this was driven by the agent's YAML configuration — no application code was written.

## Scaffold a New Agent with the CLI

Instead of writing YAML from scratch, use the CLI scaffolding commands to generate agents, workflows, and tools:

```bash
uv run astromeshctl new agent my-bot --provider ollama --model llama3.1:8b --orchestration react
```

This creates `config/agents/my-bot.agent.yaml` with a ready-to-use template. The dev server will auto-detect it if it is running.

You can also scaffold workflows and custom tools:

```bash
uv run astromeshctl new workflow data-pipeline
uv run astromeshctl new tool web_scraper --description "Scrape web pages"
```

## Ask the Copilot

The built-in copilot can answer questions about Astromesh, validate your configs, and suggest improvements:

```bash
uv run astromeshctl ask "What orchestration pattern should I use for a research agent?"
```

Pass a config file as context for targeted advice:

```bash
uv run astromeshctl ask "Is this config correct?" --context config/agents/my-bot.agent.yaml
```

## Next Steps

Now that you have Astromesh running, create your own custom agent from scratch in the [Your First Agent](/astromesh/getting-started/first-agent/) guide, or explore the full [CLI Commands](/astromesh/reference/cli-commands/) reference.
