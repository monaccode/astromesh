# Astromesh Ecosystem Design

**Date:** 2026-03-10
**Status:** Approved
**Scope:** Built-in tools, observability, CLI, copilot, multi-agent workflows, VS Code extension

## Vision

Make Astromesh the developer's preferred platform for agent orchestration by providing:

- Standard built-in tools ready to use out of the box
- Full observability for debugging and optimization
- A CLI with integrated copilot for scaffolding, running, and managing agents
- Intuitive multi-agent workflow composition at two abstraction levels
- A VS Code extension as visual layer over the CLI

Target users: enterprise developers (internal agents) and product developers (AI-powered products).

## Architecture Overview

```
Developer Experience Layer
├── astromesh CLI (core)          ← All functionality
├── VS Code Extension             ← Visual layer over CLI
└── Copilot Agent                 ← Astromesh agent that helps build agents

Runtime Layer (existing, enhanced)
├── Built-in Tools (19 tools)     ← New standard catalog
├── Orchestration (enhanced)      ← Composition + Workflow YAML
├── Observability                 ← Tracing, metrics, dashboard
└── Core Services                 ← ModelRouter, Memory, RAG, Guardrails (existing)
```

### Shared Contracts

All sub-projects share 3 stable contracts:

1. **Agent YAML schema** (`astromesh/v1 Agent`) — existing, extended with `type: builtin` for tools and observability config
2. **Workflow YAML schema** (`astromesh/v1 Workflow`) — new, for multi-agent DAGs
3. **Observability API** (`/v1/traces/`, `/v1/metrics/`) — new REST endpoints consumed by CLI, VS Code, and dashboard

## Sub-projects and Dependencies

```
[1] Built-in Tools + Observability  ──→  [2] CLI + Copilot
                                    ──→  [3] Multi-agent Enhanced
                                                ──→  [4] Workflow YAML + Dashboard
                                                              ──→  [5] VS Code Extension
```

- Sub-project 1: no dependencies, foundational
- Sub-projects 2 and 3: can run in parallel after 1
- Sub-project 4: requires 3 (multi-agent)
- Sub-project 5: requires 2 (CLI) and 4 (dashboard/workflows to visualize)

---

## Sub-project 1: Built-in Tools + Observability

### Tool Catalog (19 tools)

**Hybrid approach:** lightweight tools as Python built-in modules, heavy tools as packaged MCP servers.

#### Information & Search


| Tool         | Type    | Description                                          |
| ------------ | ------- | ---------------------------------------------------- |
| `web_search` | builtin | Web search (SearXNG self-hosted or Tavily/Brave API) |
| `web_scrape` | builtin | Extract content from URL (HTML→markdown)             |
| `wikipedia`  | builtin | Wikipedia API query                                  |


#### HTTP & APIs


| Tool            | Type    | Description                                        |
| --------------- | ------- | -------------------------------------------------- |
| `http_request`  | builtin | Generic GET/POST/PUT/DELETE with configurable auth |
| `graphql_query` | builtin | Execute GraphQL queries                            |


#### Files & Data


| Tool         | Type    | Description                                     |
| ------------ | ------- | ----------------------------------------------- |
| `read_file`  | builtin | Read local files (text, CSV, JSON, PDF)         |
| `write_file` | builtin | Write/create files                              |
| `sql_query`  | builtin | Execute SQL queries (PostgreSQL, SQLite, MySQL) |


#### Code & Computation


| Tool               | Type | Description                        |
| ------------------ | ---- | ---------------------------------- |
| `code_interpreter` | mcp  | Execute Python in sandbox (Docker) |
| `shell_exec`       | mcp  | Execute shell commands in sandbox  |


#### Communication


| Tool           | Type    | Description                        |
| -------------- | ------- | ---------------------------------- |
| `send_email`   | builtin | Send email via SMTP                |
| `send_slack`   | builtin | Send Slack message via webhook/API |
| `send_webhook` | builtin | Generic POST to webhook URL        |


#### Utilities


| Tool             | Type    | Description                                                                     |
| ---------------- | ------- | ------------------------------------------------------------------------------- |
| `datetime_now`   | builtin | Current date/time with timezone                                                 |
| `json_transform` | builtin | Transform JSON with JMESPath/JSONPath                                           |
| `text_summarize` | builtin | Summarize long text (uses agent's model)                                        |
| `generate_image` | builtin | Generate image (configurable provider: DALL-E, Stable Diffusion, etc.)          |
| `cache_store`    | builtin | Temporary key-value cache (Redis/in-memory) for sharing data between tool calls |


#### RAG (existing, exposed as tools)


| Tool         | Type    | Description                       |
| ------------ | ------- | --------------------------------- |
| `rag_query`  | builtin | Wrapper over existing RAGPipeline |
| `rag_ingest` | builtin | Ingest document into RAG pipeline |


### Tool Architecture

#### File Structure

```
astromesh/tools/
├── __init__.py              # ToolLoader: auto-discovery and registration
├── base.py                  # BuiltinTool ABC + decorators
├── builtin/
│   ├── __init__.py
│   ├── web_search.py        # web_search, web_scrape, wikipedia
│   ├── http.py              # http_request, graphql_query
│   ├── files.py             # read_file, write_file
│   ├── database.py          # sql_query
│   ├── communication.py     # send_email, send_slack, send_webhook
│   ├── utilities.py         # datetime_now, json_transform, cache_store
│   ├── ai.py                # text_summarize, generate_image
│   └── rag.py               # rag_query, rag_ingest (wrappers)
└── mcp_servers/
    ├── __init__.py
    ├── code_interpreter/     # Dockerfile + MCP server
    └── shell_exec/           # Dockerfile + MCP server
```

#### Base Class

```python
class BuiltinTool(ABC):
    name: str
    description: str
    parameters: dict          # JSON Schema for LLM function calling
    config_schema: dict       # JSON Schema for YAML config

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult
    async def validate_config(self, config: dict) -> None
    async def health_check(self) -> bool
```

**ToolContext** provides controlled access to:

- `trace_span` — for emitting observability spans
- `agent_config` — config of invoking agent (read-only)
- `cache` — shared cache_store
- `secrets` — resolved env vars from YAML

**ToolResult** standardizes responses:

```python
@dataclass
class ToolResult:
    success: bool
    data: Any
    metadata: dict
    error: str | None
```

#### Auto-discovery and Registration

When runtime loads an agent with `type: builtin`:

1. `ToolLoader` scans `astromesh/tools/builtin/` for `BuiltinTool` subclasses
2. Registers each in existing `ToolRegistry` with `type=INTERNAL`
3. Passes YAML `config` as configuration
4. Tools with invalid config fail at startup, not runtime

#### Security Defaults

- `sql_query`: `read_only: true` by default, optional table whitelist
- `http_request`: 30s timeout, 5MB max response, no localhost access by default
- `write_file`: restricted to configurable directory (`allowed_paths`)
- `shell_exec` / `code_interpreter`: MCP only, Docker container isolated
- `send_email` / `send_slack`: rate limit by default (10/min)

#### YAML Usage

```yaml
tools:
  # Built-in: just name, zero config
  - name: web_search
    type: builtin

  # Built-in with config
  - name: sql_query
    type: builtin
    config:
      connection_string: ${DATABASE_URL}
      read_only: true

  # Packaged MCP server
  - name: code_interpreter
    type: mcp_stdio
    config:
      sandbox: docker
      timeout_seconds: 30
```

### Observability

#### Three Pillars

**1. Structured Tracing**

Each execution generates a trace tree:

```
Trace: run_abc123
├── Span: agent.input_guardrails (2ms)
├── Span: agent.memory_build (15ms)
│   ├── Span: memory.conversational (8ms)
│   └── Span: memory.semantic_search (7ms)
├── Span: agent.prompt_render (1ms)
├── Span: orchestration.react (3200ms)
│   ├── Span: llm.complete (800ms) → {provider: ollama, model: llama3.1, tokens_in: 450, tokens_out: 120}
│   ├── Span: tool.web_search (1500ms) → {results: 5}
│   ├── Span: llm.complete (700ms)
│   └── Span: tool.sql_query (200ms) → {rows: 12}
├── Span: agent.output_guardrails (3ms)
└── Span: agent.memory_persist (10ms)
```

Each span: `trace_id`, `span_id`, `parent_span_id`, `name`, `start_time`, `duration_ms`, `status`, `attributes`, `events`.

**2. Metrics**


| Metric                     | Type      | Description                    |
| -------------------------- | --------- | ------------------------------ |
| `agent.runs.total`         | counter   | Executions by agent/status     |
| `agent.run.duration_ms`    | histogram | End-to-end latency             |
| `llm.tokens.input`         | counter   | Input tokens by provider/model |
| `llm.tokens.output`        | counter   | Output tokens                  |
| `llm.cost.usd`             | counter   | Estimated accumulated cost     |
| `tool.calls.total`         | counter   | Calls by tool/status           |
| `tool.call.duration_ms`    | histogram | Latency by tool                |
| `orchestration.iterations` | histogram | Iterations by pattern          |
| `memory.operations`        | counter   | Reads/writes by backend        |


**3. Structured Logging** — JSON to stdout, compatible with any collector:

```json
{
  "timestamp": "2026-03-10T14:30:00Z",
  "level": "info",
  "trace_id": "run_abc123",
  "span_id": "span_456",
  "agent": "sales-qualifier",
  "event": "tool.executed",
  "tool": "web_search",
  "duration_ms": 1500,
  "status": "success"
}
```

#### Runtime Integration

- A **TracingContext** is created at the start of each `runtime.run()` and propagated via contextvars
- Each component (memory, orchestration, tools, providers) opens/closes spans automatically — **zero configuration** for agent developers
- Data is emitted to a configurable **collector**:
  - `stdout` (default) — JSON logs
  - `otlp` — OpenTelemetry Protocol (compatible with Jaeger, Grafana Tempo, etc.)
  - `internal` — stores in SQLite/PostgreSQL for built-in dashboard

#### Query API

```
GET  /v1/traces/?agent=sales-qualifier&limit=20     → List of traces
GET  /v1/traces/{trace_id}                           → Full trace with spans
GET  /v1/metrics/?agent=sales-qualifier&window=1h    → Aggregated metrics
GET  /v1/metrics/cost?group_by=agent&window=24h      → Cost by agent
```

#### Agent YAML Config (optional, sensible defaults)

```yaml
spec:
  observability:
    tracing: true
    metrics: true
    collector: stdout
    otlp_endpoint: ${OTEL_ENDPOINT}
    sample_rate: 1.0
```

---

## Sub-project 2: CLI + Copilot

### CLI Commands

```bash
# Scaffolding
astromesh init                          # Initialize project
astromesh new agent <name>              # Generate agent YAML interactively
astromesh new workflow <name>           # Generate Workflow YAML
astromesh new tool <name>              # Scaffold custom tool

# Execution
astromesh run <agent> "query"           # Run agent locally
astromesh run <workflow> --input '{}'   # Run workflow
astromesh dev                           # Dev mode: hot-reload + API server

# Observability
astromesh traces <agent> --last 10      # Recent traces
astromesh trace <trace_id>              # Trace detail (span tree)
astromesh metrics <agent> --window 1h   # Aggregated metrics
astromesh cost --window 24h             # Cost summary

# Tools
astromesh tools list                    # Available tools
astromesh tools test <name> '{args}'    # Test a tool in isolation

# Validation
astromesh validate                      # Validate all project YAMLs
astromesh doctor                        # Check dependencies, providers, connections

# Copilot
astromesh ask "anything"                # Interactive copilot
```

### Copilot

The copilot is an Astromesh agent (`config/agents/astromesh-copilot.agent.yaml`) that uses Astromesh's own built-in tools plus CLI-specific internal tools (`validate_yaml`, `list_builtin_tools`, `analyze_trace`, `run_agent_test`).

Capabilities: scaffolding, debugging (trace analysis), optimization (token/cost advice), testing (simulated queries), documentation generation.

### Technical Implementation

- Python package: `pip install astromesh-cli` (or `uv add astromesh-cli`)
- Uses `typer` for commands
- Consumes Astromesh REST API for run/traces/metrics
- Copilot runs locally using the same runtime
- Global config at `~/.astromesh/config.yaml`

---

## Sub-project 3: Multi-agent Enhanced

### Agents as Tools

```yaml
tools:
  - name: qualify-lead
    type: agent
    agent: sales-qualifier
    context_transform: "{company: data.company, summary: data.summary}"
```

The orchestrator treats `type: agent` like any tool — calls with arguments, receives ToolResult. Internally calls `runtime.run(agent_name, ...)`.

### Context Transforms

JMESPath transformations on previous step output:

```yaml
# No transform: pass everything (default)
- name: agent-b
  type: agent
  agent: my-agent

# With transform: filter/reshape
- name: agent-b
  type: agent
  agent: my-agent
  context_transform: "{score: data.score || `0`, name: data.name || `unknown`}"
```

---

## Sub-project 4: Workflow YAML + Dashboard

### Workflow Schema

```yaml
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: lead-qualification-pipeline
spec:
  trigger: api           # api | schedule | webhook | event

  steps:
    - name: research
      agent: web-researcher
      input: "{{ trigger.query }}"

    - name: qualify
      agent: sales-qualifier
      input: "{{ steps.research.output }}"
      context_transform: "{company: data.company}"

    - name: decide
      switch:
        - when: "{{ steps.qualify.output.data.score > 7 }}"
          goto: send-email
        - default:
          goto: log-and-skip

    - name: send-email
      agent: email-composer
      input: "{{ steps.qualify.output }}"

    - name: log-and-skip
      tool: cache_store
      arguments:
        key: "skipped_{{ trigger.id }}"
        value: "{{ steps.qualify.output }}"

  observability:
    collector: internal
```

### Dashboard

Built-in web UI consuming `/v1/traces/` and `/v1/metrics/` endpoints. Displays trace trees, metric charts, cost breakdowns, and workflow visualizations.

---

## Sub-project 5: VS Code Extension

### Features


| Feature             | Implementation                                       |
| ------------------- | ---------------------------------------------------- |
| YAML IntelliSense   | JSON Schema for `*.agent.yaml` and `*.workflow.yaml` |
| Workflow visualizer | Panel rendering Workflow YAML as node graph          |
| Run agent           | Play button → executes via CLI                       |
| Traces panel        | Sidebar with expandable span trees                   |
| Metrics dashboard   | Webview with token/cost/latency charts               |
| Copilot chat        | Chat panel invoking `astromesh ask`                  |
| Diagnostics         | Equivalent to `astromesh doctor`                     |


### Architecture

```
VS Code Extension
├── Language Server (YAML schema validation + autocompletion)
├── Webview panels (workflow viz, metrics dashboard)
└── CLI wrapper (all commands via astromesh CLI)
     ↓
  astromesh CLI  ← single source of logic
     ↓
  Astromesh API server
```

The extension has **no logic of its own** — everything goes through the CLI.

---

## Clarifications and Decisions

Issues identified during spec review, with resolutions.

### Tool Type Mapping

- `type: builtin` in agent YAML is a **user-facing alias** that maps internally to `ToolType.INTERNAL`
- Existing `type: internal` tools continue to work unchanged
- The `ToolLoader` resolves `builtin` → looks up in the built-in catalog; `internal` → uses inline handler as today
- A new `BUILTIN` enum value is NOT added — it's syntactic sugar in YAML parsing

### ToolResult Migration

- `ToolResult` dataclass replaces the current `dict` return from `ToolRegistry.execute()`
- Migration: `execute()` returns `ToolResult`; a `.to_dict()` method preserves backward compat for existing orchestration patterns
- Orchestration patterns are updated incrementally to use `ToolResult` directly

### Expression Language: Jinja2 Everywhere

- **Decision:** Use Jinja2 for all expressions — `context_transform`, `input`, `switch` conditions
- JMESPath was considered but mixing two languages is worse than one slightly less specialized language
- Jinja2 is already used for prompts, so developers already know it
- `context_transform` becomes a Jinja2 template that outputs JSON: `context_transform: '{"company": "{{ data.company }}"}'`

### Supervisor/Swarm vs `type: agent` Tools

- `type: agent` is the **new unified mechanism** for agent composition
- Supervisor pattern uses `type: agent` tools as its workers (replaces internal `_workers` dict)
- Swarm pattern uses `type: agent` tools for handoff targets
- The patterns provide the coordination logic; `type: agent` provides the invocation mechanism

### Observability: Relation to Existing Code

- Existing `TelemetryManager` (OTLP gRPC) becomes the `otlp` collector backend
- Existing `MetricsCollector` (Prometheus) is preserved as an optional export alongside the new metrics
- Existing `CostTracker` (Rust-accelerated) is wrapped by the `llm.cost.usd` metric — not replaced
- `internal` collector uses async buffered writes (batch of 50 or every 5s, whichever first) to avoid per-span DB overhead
- Metric naming: spec uses dot notation (`agent.runs.total`) as the canonical name; Prometheus export converts to underscore (`astromesh_agent_runs_total`)
- `sample_rate` applies to **traces only** — metrics are never sampled

### Workflow Error Handling (Sub-project 4)

```yaml
steps:
  - name: qualify
    agent: sales-qualifier
    input: "{{ steps.research.output }}"
    retry:
      max_attempts: 3
      backoff: exponential     # exponential | fixed
      initial_delay_seconds: 2
    timeout_seconds: 60
    on_error: log-and-skip     # goto step name, or "fail" to abort workflow

  - name: log-and-skip
    tool: cache_store
    arguments:
      key: "error_{{ trigger.id }}"
      value: "{{ error.message }}"
```

- Each step can have `retry`, `timeout_seconds`, and `on_error`
- `on_error` references another step name, or `"fail"` to abort the workflow
- Workflow-level `timeout_seconds` in spec for overall deadline
- Webhook/event triggers include deduplication via `trigger.id`

### Workflow Trigger Types (Sub-project 4)

- `api`: invoked via `POST /v1/workflows/{name}/run` — request body becomes `trigger`
- `schedule`: cron syntax, executed by an in-process scheduler (APScheduler or similar)
- `webhook`: unique URL per workflow `POST /v1/workflows/{name}/webhook` — payload becomes `trigger`
- `event`: internal pub/sub (Redis Pub/Sub or in-memory) — listens for named events from other agents/workflows

### Copilot Security Model (Sub-project 2)

- **Filesystem:** read-only access to `./config/` and `./docs/`. Write access only to `./config/agents/` and `./config/workflows/` for generated YAMLs.
- **Agent execution:** can run agents in **dry-run mode** (no side effects, no external tool calls) for testing
- **System access:** no shell access, no Docker access, no network access beyond the Astromesh API
- **Explicit confirmation:** destructive actions (overwrite existing YAML, delete agent) require user confirmation in CLI

### CLI Packaging (Sub-project 2)

- CLI ships as part of the `astromesh` package with an extra: `uv sync --extra cli`
- Installs `astromesh` as a CLI entry point via `[project.scripts]` in `pyproject.toml`
- No separate package — single monorepo with optional extras (consistent with current `--extra all` pattern)

### Tool Catalog Adjustments

- `generate_image` → moved to **MCP server** (requires external API/GPU, not lightweight)
- `cache_store` → scope is **per-workflow-run** (isolated), TTL configurable with default 1h, backend: Redis if available, in-memory fallback
- `text_summarize` → creates a **nested span** in tracing, cost tracked separately under `tool.text_summarize` metric, does NOT count against orchestration iteration limit
- Total tools: **18 builtin + 3 MCP servers** (code_interpreter, shell_exec, generate_image)

