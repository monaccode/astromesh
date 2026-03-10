# CLI + Copilot Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `astromeshctl` with scaffolding, execution, observability, tools, validation, and copilot commands — turning the CLI from a status dashboard into a full development workflow tool.

**Architecture:** New command modules follow the existing Typer pattern (`cli/commands/*.py`). Commands that need the daemon call `cli.client` (extended with new methods). Scaffolding uses Jinja2 templates. The copilot command boots a local `AgentRuntime` with a purpose-built `astromesh-copilot` agent that has sandboxed filesystem and API access. Workflow `run` is stubbed (Sub-project 4).

**Tech Stack:** Python 3.12+, Typer, Rich, Jinja2 (templates), httpx (client), existing AgentRuntime

**Spec:** `docs/superpowers/specs/2026-03-10-astromesh-ecosystem-design.md`

**Depends on:** Sub-project 1 (Built-in Tools + Observability) — complete. Uses `/v1/traces/`, `/v1/metrics/`, `/v1/tools/builtin` endpoints.

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `cli/commands/new.py` | `astromesh new agent/workflow/tool` — scaffolding commands |
| `cli/commands/run.py` | `astromesh run <agent>` — execute agent via API; workflow stub |
| `cli/commands/dev.py` | `astromesh dev` — hot-reload dev server |
| `cli/commands/traces.py` | `astromesh traces/trace` — observability trace commands |
| `cli/commands/metrics.py` | `astromesh metrics/cost` — aggregated metrics + cost summary |
| `cli/commands/tools.py` | `astromesh tools list/test` — tool discovery and testing |
| `cli/commands/validate.py` | `astromesh validate` — validate all project YAMLs |
| `cli/commands/ask.py` | `astromesh ask` — copilot interface |
| `cli/templates/agent.yaml.j2` | Jinja2 template for agent scaffolding |
| `cli/templates/workflow.yaml.j2` | Jinja2 template for workflow scaffolding |
| `cli/templates/tool.py.j2` | Jinja2 template for custom tool scaffolding |
| `config/agents/astromesh-copilot.agent.yaml` | Copilot agent definition |
| `tests/test_cli_new.py` | Tests for scaffolding commands |
| `tests/test_cli_run.py` | Tests for run commands |
| `tests/test_cli_traces.py` | Tests for traces/metrics commands |
| `tests/test_cli_tools.py` | Tests for tools list/test commands |
| `tests/test_cli_validate.py` | Tests for validate command |
| `tests/test_cli_ask.py` | Tests for copilot command |

### Modified Files

| File | Changes |
|------|---------|
| `cli/main.py` | Register new command groups: `new`, `run`, `dev`, `traces`, `metrics`, `tools`, `validate`, `ask` |
| `cli/client.py` | Add `api_post_stream()`, increase timeout for run/ask; add helpers for traces, metrics, tools endpoints |
| `cli/output.py` | Add `print_trace_tree()`, `print_metrics_table()`, `print_cost_table()`, `print_tool_list()` |
| `pyproject.toml` | Add `jinja2` to `cli` extras (already a base dep, but explicit is better) |

---

## Chunk 1: Scaffolding — `new agent`, `new workflow`, `new tool`

### Task 1: Jinja2 templates for scaffolding

**Files:**
- Create: `cli/templates/agent.yaml.j2`, `cli/templates/workflow.yaml.j2`, `cli/templates/tool.py.j2`
- Test: `tests/test_cli_new.py`

- [ ] **Step 1: Write failing tests for template rendering**

```python
# tests/test_cli_new.py
import pytest
from pathlib import Path

from cli.commands.new import render_agent_template, render_workflow_template, render_tool_template


class TestTemplateRendering:
    def test_render_agent_template_minimal(self):
        result = render_agent_template(name="test-bot", provider="ollama", model="llama3.1:8b")
        assert "name: test-bot" in result
        assert "apiVersion: astromesh/v1" in result
        assert "kind: Agent" in result
        assert "ollama" in result

    def test_render_agent_template_with_tools(self):
        result = render_agent_template(
            name="helper", provider="openai", model="gpt-4o", tools=["web_search", "http_request"]
        )
        assert "web_search" in result
        assert "http_request" in result

    def test_render_workflow_template(self):
        result = render_workflow_template(name="my-workflow")
        assert "name: my-workflow" in result
        assert "kind: Workflow" in result

    def test_render_tool_template(self):
        result = render_tool_template(name="my_custom_tool", description="Does something useful")
        assert "class MyCustomToolTool(BuiltinTool)" in result
        assert "Does something useful" in result
```

- [ ] **Step 2: Create Jinja2 templates**

Create `cli/templates/agent.yaml.j2` based on the schema from existing agents like `config/agents/support-agent.agent.yaml`. Template variables: `name`, `display_name`, `description`, `provider`, `model`, `orchestration_pattern`, `tools`, `temperature`, `max_tokens`.

Create `cli/templates/workflow.yaml.j2` with stub Workflow schema: `apiVersion: astromesh/v1`, `kind: Workflow`, `metadata.name`, `spec.steps` (empty list placeholder).

Create `cli/templates/tool.py.j2` that generates a Python file with a class inheriting from `astromesh.tools.base.BuiltinTool`, with `name`, `description`, `parameters` properties and an `async def execute()` stub.

- [ ] **Step 3: Implement `render_*_template()` helper functions**

In `cli/commands/new.py`, implement three functions that load Jinja2 templates from `cli/templates/` using `importlib.resources` or `Path(__file__).parent.parent / "templates"` and render them with the given parameters. Verify all tests pass.

### Task 2: Interactive `new` commands with Typer

**Files:**
- Create: `cli/commands/new.py` (add Typer commands)
- Modify: `cli/main.py` (register `new` command group)
- Test: `tests/test_cli_new.py`

- [ ] **Step 1: Write failing tests for CLI commands**

```python
# tests/test_cli_new.py (append)
from typer.testing import CliRunner
from cli.main import app

runner = CliRunner()


class TestNewAgentCommand:
    def test_new_agent_non_interactive(self, tmp_path):
        result = runner.invoke(app, [
            "new", "agent", "my-bot",
            "--provider", "ollama",
            "--model", "llama3.1:8b",
            "--output-dir", str(tmp_path),
        ])
        assert result.exit_code == 0
        agent_file = tmp_path / "my-bot.agent.yaml"
        assert agent_file.exists()
        content = agent_file.read_text()
        assert "name: my-bot" in content

    def test_new_agent_refuses_overwrite_without_force(self, tmp_path):
        (tmp_path / "existing.agent.yaml").write_text("existing")
        result = runner.invoke(app, [
            "new", "agent", "existing",
            "--provider", "ollama",
            "--model", "llama3.1:8b",
            "--output-dir", str(tmp_path),
        ])
        assert result.exit_code == 0
        assert "already exists" in result.output.lower() or "overwrite" in result.output.lower()

    def test_new_tool_creates_python_file(self, tmp_path):
        result = runner.invoke(app, [
            "new", "tool", "my_checker",
            "--description", "Checks things",
            "--output-dir", str(tmp_path),
        ])
        assert result.exit_code == 0
        tool_file = tmp_path / "my_checker.py"
        assert tool_file.exists()
```

- [ ] **Step 2: Implement `new` Typer command group**

In `cli/commands/new.py`, create a `typer.Typer()` app with three sub-commands:

- `agent <name>` — Options: `--provider` (default `ollama`), `--model` (default `llama3.1:8b`), `--orchestration` (default `react`), `--tools` (list), `--output-dir` (default `./config/agents`), `--force` (overwrite). Renders template, writes `<name>.agent.yaml`, prints success with Rich.
- `workflow <name>` — Options: `--output-dir` (default `./config/workflows`), `--force`. Renders template, writes `<name>.workflow.yaml`.
- `tool <name>` — Options: `--description`, `--output-dir` (default `.`), `--force`. Renders template, writes `<name>.py`.

All commands refuse overwrite unless `--force`. All print a summary of what was created.

- [ ] **Step 3: Register `new` in `cli/main.py`**

Add `from cli.commands import new` to imports and `app.add_typer(new.app, name="new")`. Verify all tests pass.

### Task 3: Validation command

**Files:**
- Create: `cli/commands/validate.py`
- Modify: `cli/main.py`
- Test: `tests/test_cli_validate.py`

- [ ] **Step 1: Write failing tests for validate command**

```python
# tests/test_cli_validate.py
from typer.testing import CliRunner
from cli.main import app

runner = CliRunner()


def test_validate_valid_project(tmp_path):
    agents_dir = tmp_path / "config" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "test.agent.yaml").write_text(
        "apiVersion: astromesh/v1\nkind: Agent\nmetadata:\n  name: test\nspec:\n  identity:\n    display_name: Test\n"
    )
    (tmp_path / "config" / "runtime.yaml").write_text(
        "apiVersion: astromesh/v1\nkind: RuntimeConfig\nmetadata:\n  name: default\n"
    )
    result = runner.invoke(app, ["validate", "--path", str(tmp_path / "config")])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_validate_invalid_yaml(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "runtime.yaml").write_text(": bad: [yaml")
    result = runner.invoke(app, ["validate", "--path", str(config_dir)])
    assert result.exit_code == 0
    assert "error" in result.output.lower() or "failed" in result.output.lower()


def test_validate_missing_kind(tmp_path):
    agents_dir = tmp_path / "config" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "bad.agent.yaml").write_text("apiVersion: astromesh/v1\nmetadata:\n  name: bad\n")
    result = runner.invoke(app, ["validate", "--path", str(tmp_path / "config")])
    assert "error" in result.output.lower() or "failed" in result.output.lower()
```

- [ ] **Step 2: Implement validate command**

Create `cli/commands/validate.py` with a `validate` command. Reuse and extract the validation logic from `cli/commands/init.py` (`_validate_config`) into a shared function (or call it directly). Extend validation to also check: `apiVersion` is present, `kind` matches expected value for file type, `metadata.name` is present. `--path` option defaults to `./config`. Output a Rich table with file, status (valid/error), and message.

- [ ] **Step 3: Register in `cli/main.py` and verify tests pass**

Add `from cli.commands import validate` and `app.command("validate")(validate.validate_command)`. Run tests.

---

## Chunk 2: Execution + Observability — `run`, `dev`, `traces`, `metrics`

### Task 4: Extend `cli/client.py` with new API methods

**Files:**
- Modify: `cli/client.py`
- Test: `tests/test_cli_run.py` (client tests)

- [ ] **Step 1: Write failing tests for new client methods**

```python
# tests/test_cli_run.py (client portion)
from unittest.mock import MagicMock, patch
from cli.client import api_post_with_timeout, api_get_params


def test_api_post_with_timeout():
    mock_response = MagicMock()
    mock_response.json.return_value = {"result": "ok"}
    mock_response.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_response) as mock_post:
        result = api_post_with_timeout("/v1/agents/test/run", json={"query": "hi"}, timeout=30.0)
    assert result == {"result": "ok"}
    mock_post.assert_called_once()


def test_api_get_params():
    mock_response = MagicMock()
    mock_response.json.return_value = {"traces": []}
    mock_response.raise_for_status = MagicMock()
    with patch("cli.client.httpx.get", return_value=mock_response) as mock_get:
        result = api_get_params("/v1/traces/", params={"agent": "test", "limit": 10})
    assert result == {"traces": []}
```

- [ ] **Step 2: Implement new client methods**

Add to `cli/client.py`:
- `api_post_with_timeout(path, json=None, timeout=30.0)` — like `api_post` but with configurable timeout for long-running agent calls.
- `api_get_params(path, params=None, timeout=5.0)` — GET with query parameters dict.

Keep the existing `api_get` and `api_post` unchanged for backwards compatibility.

### Task 5: `run` command — execute agents

**Files:**
- Create: `cli/commands/run.py`
- Modify: `cli/main.py`
- Test: `tests/test_cli_run.py`

- [ ] **Step 1: Write failing tests for run command**

```python
# tests/test_cli_run.py (append)
from typer.testing import CliRunner
from cli.main import app

runner = CliRunner()


def test_run_agent():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "response": "Hello from agent",
        "trace_id": "abc-123",
        "tokens_used": 150,
    }
    mock_response.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_response):
        result = runner.invoke(app, ["run", "support-agent", "What is your return policy?"])
    assert result.exit_code == 0
    assert "Hello from agent" in result.output


def test_run_agent_with_json_output():
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "ok", "trace_id": "x"}
    mock_response.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_response):
        result = runner.invoke(app, ["run", "support-agent", "hi", "--json"])
    assert result.exit_code == 0
    assert "trace_id" in result.output


def test_run_workflow_stub():
    result = runner.invoke(app, ["run", "my-workflow", "--workflow", "--input", "{}"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output.lower() or "sub-project 4" in result.output.lower()
```

- [ ] **Step 2: Implement `run` command**

Create `cli/commands/run.py` with a Typer app:

- `run <name> <query>` — POST to `/v1/agents/{name}/run` with `{"query": query, "session_id": session_id}`. Options: `--session` (default: auto-generated UUID), `--json`, `--timeout` (default 60s). Display: agent response text, trace_id, tokens used. Use `api_post_with_timeout`.
- `--workflow` flag + `--input` — prints "Workflow execution is not yet implemented (Sub-project 4)" and exits.

- [ ] **Step 3: Register in `cli/main.py`**

Add `app.command("run")(run.run_command)` (not a Typer group — single command with arguments). Verify tests pass.

### Task 6: `dev` command — hot-reload dev server

**Files:**
- Create: `cli/commands/dev.py`
- Modify: `cli/main.py`
- Test: `tests/test_cli_run.py` (reuse file)

- [ ] **Step 1: Write failing test for dev command**

```python
# tests/test_cli_run.py (append)
def test_dev_command_shows_startup_info(monkeypatch):
    """Test that dev prints startup info before launching uvicorn."""
    import cli.commands.dev as dev_mod
    calls = []
    monkeypatch.setattr(dev_mod, "_launch_uvicorn", lambda **kw: calls.append(kw))
    result = runner.invoke(app, ["dev", "--port", "9000", "--no-open"])
    assert result.exit_code == 0
    assert len(calls) == 1
    assert calls[0]["port"] == 9000
```

- [ ] **Step 2: Implement `dev` command**

Create `cli/commands/dev.py`:

- `dev` command — Options: `--host` (default `0.0.0.0`), `--port` (default `8000`), `--config` (default `./config`), `--no-open` (skip browser open). Prints a Rich panel with "Astromesh Dev Server" banner showing host:port and config path. Calls `_launch_uvicorn(host, port, reload=True, reload_dirs=["astromesh", "config"])` which wraps `uvicorn.run("astromesh.api.main:app", ...)`. Extract `_launch_uvicorn` as a separate function for testability.

- [ ] **Step 3: Register in `cli/main.py` and verify**

Add `app.command("dev")(dev.dev_command)`.

### Task 7: `traces` and `metrics` commands + output helpers

**Files:**
- Create: `cli/commands/traces.py`, `cli/commands/metrics.py`
- Modify: `cli/output.py`, `cli/main.py`
- Test: `tests/test_cli_traces.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli_traces.py
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner
from cli.main import app

runner = CliRunner()


def test_traces_list():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "traces": [
            {"trace_id": "abc", "agent": "support-agent", "started_at": "2026-03-10T10:00:00", "duration_ms": 1200, "status": "ok"},
            {"trace_id": "def", "agent": "support-agent", "started_at": "2026-03-10T09:00:00", "duration_ms": 800, "status": "ok"},
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.get", return_value=mock_resp):
        result = runner.invoke(app, ["traces", "support-agent", "--last", "10"])
    assert result.exit_code == 0
    assert "abc" in result.output


def test_trace_detail():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "trace_id": "abc",
        "agent": "support-agent",
        "spans": [
            {"name": "agent.run", "duration_ms": 1200, "children": [
                {"name": "model.complete", "duration_ms": 900, "children": []},
                {"name": "tool.web_search", "duration_ms": 250, "children": []},
            ]},
        ],
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.get", return_value=mock_resp):
        result = runner.invoke(app, ["trace", "abc"])
    assert result.exit_code == 0
    assert "agent.run" in result.output


def test_metrics():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "counters": {"agent.runs": 42, "tool.calls": 108},
        "histograms": {"agent.latency_ms": {"count": 42, "avg": 1100.5, "min": 200, "max": 5000}},
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.get", return_value=mock_resp):
        result = runner.invoke(app, ["metrics"])
    assert result.exit_code == 0
    assert "agent.runs" in result.output or "42" in result.output


def test_cost():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "counters": {"cost.total_usd": 0},
        "histograms": {"agent.cost_usd": {"count": 10, "sum": 0.45, "avg": 0.045}},
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.get", return_value=mock_resp):
        result = runner.invoke(app, ["cost"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Add output helpers to `cli/output.py`**

Add to `cli/output.py`:
- `print_trace_list(traces: list[dict])` — Rich table with columns: Trace ID (truncated to 8 chars), Agent, Started At, Duration, Status.
- `print_trace_tree(trace: dict)` — Rich Tree rendering of span hierarchy. Root span at top, children indented. Each node shows `name (duration_ms ms)`.
- `print_metrics_table(data: dict)` — Two Rich tables: one for counters (Name, Value), one for histograms (Name, Count, Avg, Min, Max).
- `print_cost_table(data: dict)` — Rich table focused on cost histograms with USD formatting.

- [ ] **Step 3: Implement `traces` and `metrics` commands**

`cli/commands/traces.py`:
- `traces <agent>` command — Options: `--last` (default 10), `--json`. Calls `api_get_params("/v1/traces/", params={"agent": agent, "limit": last})`. Renders with `print_trace_list`.
- Also register a top-level `trace <trace_id>` command — Calls `api_get(f"/v1/traces/{trace_id}")`. Renders with `print_trace_tree`.

`cli/commands/metrics.py`:
- `metrics` command — Options: `--agent` (filter, optional), `--json`. Calls `api_get("/v1/metrics/")`. Renders with `print_metrics_table`.
- `cost` command — Options: `--json`. Calls same endpoint, renders with `print_cost_table`.

- [ ] **Step 4: Register in `cli/main.py` and verify**

Register `traces` as a command group, `trace` as a top-level command, `metrics` as a command group, `cost` as a top-level command. Run all tests.

---

## Chunk 3: Tools + Validation polish

### Task 8: `tools list` and `tools test` commands

**Files:**
- Create: `cli/commands/tools.py`
- Modify: `cli/main.py`, `cli/output.py`
- Test: `tests/test_cli_tools.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli_tools.py
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner
from cli.main import app

runner = CliRunner()


def test_tools_list():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "tools": [
            {"name": "web_search", "description": "Search the web", "parameters": {"query": {"type": "string"}}},
            {"name": "http_request", "description": "Make HTTP requests", "parameters": {}},
        ],
        "count": 2,
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.get", return_value=mock_resp):
        result = runner.invoke(app, ["tools", "list"])
    assert result.exit_code == 0
    assert "web_search" in result.output
    assert "http_request" in result.output


def test_tools_test():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"tool": "web_search", "result": {"data": "results"}, "status": "ok"}
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_resp):
        result = runner.invoke(app, ["tools", "test", "web_search", '{"query": "test"}'])
    assert result.exit_code == 0
    assert "results" in result.output or "ok" in result.output
```

- [ ] **Step 2: Add `print_tool_list()` to `cli/output.py`**

Rich table with columns: Name (cyan), Description, Parameters (dim, comma-separated param names).

- [ ] **Step 3: Implement tools commands**

`cli/commands/tools.py`:
- `list` — GET `/v1/tools/builtin`, render with `print_tool_list`. Options: `--json`.
- `test <name> <args_json>` — POST `/v1/tools/execute` with `{"tool_name": name, "arguments": json.loads(args_json)}`. Display result as JSON. Options: `--json`.

- [ ] **Step 4: Register in `cli/main.py` and verify**

`app.add_typer(tools.app, name="tools")`.

---

## Chunk 4: Copilot — `ask` command + agent definition

### Task 9: Copilot agent YAML definition

**Files:**
- Create: `config/agents/astromesh-copilot.agent.yaml`

- [ ] **Step 1: Create copilot agent YAML**

```yaml
# config/agents/astromesh-copilot.agent.yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: astromesh-copilot
  version: "0.1.0"
  namespace: system

spec:
  identity:
    display_name: "Astromesh Copilot"
    description: "CLI assistant for Astromesh development — validates configs, explains traces, suggests improvements"

  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"
      parameters:
        temperature: 0.3
        max_tokens: 4096

  prompts:
    system: |
      You are the Astromesh Copilot, an expert assistant for the Astromesh AI agent orchestration platform.

      You help developers:
      - Create and validate agent YAML configurations
      - Debug trace data and identify performance issues
      - Explain orchestration patterns (ReAct, PlanAndExecute, etc.)
      - Suggest built-in tools for specific use cases
      - Troubleshoot provider connectivity and routing

      You have access to tools for reading project config files, validating YAML, listing available tools, and analyzing traces.
      Always be precise and reference specific file paths and configuration keys.
      When suggesting changes, show the exact YAML diff.

  orchestration:
    pattern: react
    max_iterations: 5
    timeout: 30

  tools:
    - type: builtin
      name: validate_yaml
    - type: builtin
      name: list_builtin_tools
    - type: builtin
      name: read_file

  memory:
    conversational:
      backend: sqlite
      strategy: sliding_window
      max_turns: 20

  permissions:
    filesystem:
      read: ["./config/", "./docs/"]
      write: ["./config/agents/", "./config/workflows/"]
    network:
      allowed: ["localhost:8000"]
    execution:
      dry_run: true
```

- [ ] **Step 2: Verify the YAML is valid by running `astromesh validate`**

(Or manually parse with `yaml.safe_load` in a test.)

### Task 10: `ask` command — copilot CLI interface

**Files:**
- Create: `cli/commands/ask.py`
- Modify: `cli/main.py`
- Test: `tests/test_cli_ask.py`

- [ ] **Step 1: Write failing tests for ask command**

```python
# tests/test_cli_ask.py
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner
from cli.main import app

runner = CliRunner()


def test_ask_sends_query_to_copilot():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "response": "To create a new agent, run: astromesh new agent my-bot",
        "trace_id": "copilot-123",
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_resp):
        result = runner.invoke(app, ["ask", "How do I create a new agent?"])
    assert result.exit_code == 0
    assert "astromesh new agent" in result.output


def test_ask_with_context_file(tmp_path):
    config_file = tmp_path / "test.agent.yaml"
    config_file.write_text("apiVersion: astromesh/v1\nkind: Agent\n")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "The agent config looks valid.", "trace_id": "x"}
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_resp):
        result = runner.invoke(app, ["ask", "Review this config", "--context", str(config_file)])
    assert result.exit_code == 0


def test_ask_dry_run():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "Dry run: would create agent", "trace_id": "x"}
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_resp):
        result = runner.invoke(app, ["ask", "Create an agent for me", "--dry-run"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Implement `ask` command**

`cli/commands/ask.py`:
- `ask <query>` — Options: `--context <file_path>` (attach a file's content to the query), `--dry-run` (pass `dry_run: true` to agent), `--session` (reuse session for multi-turn), `--json`.
- Sends POST to `/v1/agents/astromesh-copilot/run` with body: `{"query": query, "session_id": session, "metadata": {"context_file": content_if_provided, "dry_run": dry_run}}`.
- Displays response with Rich Markdown rendering (`rich.markdown.Markdown`).
- If `--context` is provided, reads the file (with sandboxing check: must be under `./config/` or `./docs/`), appends content to query as `\n\n---\nContext from {path}:\n{content}`.

- [ ] **Step 3: Security validation for context files**

Add a `_validate_context_path(path: Path) -> bool` function that checks:
- Path resolves to within `./config/` or `./docs/` (prevent directory traversal).
- File exists and is readable.
- File size < 100KB.
Print error and exit if validation fails.

- [ ] **Step 4: Register in `cli/main.py` and verify all tests pass**

`app.command("ask")(ask.ask_command)`.

### Task 11: Final integration — `cli/main.py` wiring + smoke test

**Files:**
- Modify: `cli/main.py`
- Test: all test files

- [ ] **Step 1: Verify complete `cli/main.py` registration**

Final `cli/main.py` should import and register all new modules:

```python
from cli.commands import (
    agents, ask, config, dev, doctor, init, mesh, metrics, new,
    peers, providers, run, services, status, tools, traces, validate,
)

# Existing
app.add_typer(status.app, name="status")
app.add_typer(doctor.app, name="doctor")
app.add_typer(agents.app, name="agents")
app.add_typer(providers.app, name="providers")
app.add_typer(config.app, name="config")
app.add_typer(mesh.app, name="mesh")
app.add_typer(peers.app, name="peers")
app.add_typer(services.app, name="services")
app.command("init")(init.init_command)

# New command groups
app.add_typer(new.app, name="new")
app.add_typer(traces.app, name="traces")
app.add_typer(tools.app, name="tools")

# New top-level commands
app.command("run")(run.run_command)
app.command("dev")(dev.dev_command)
app.command("validate")(validate.validate_command)
app.command("ask")(ask.ask_command)
app.command("trace")(traces.trace_command)
app.command("metrics")(metrics.metrics_command)
app.command("cost")(metrics.cost_command)
```

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest tests/test_cli_new.py tests/test_cli_run.py tests/test_cli_traces.py tests/test_cli_tools.py tests/test_cli_validate.py tests/test_cli_ask.py tests/test_cli.py -v
```

- [ ] **Step 3: Manual smoke test of `--help` for all commands**

Verify `astromeshctl --help` shows all new commands, and each sub-command `--help` renders correctly. Fix any Typer registration issues.

---

## Summary

| Chunk | Tasks | Files Created | Files Modified |
|-------|-------|---------------|----------------|
| 1: Scaffolding | 1-3 | `new.py`, `validate.py`, 3 templates, 2 test files | `main.py` |
| 2: Execution + Observability | 4-7 | `run.py`, `dev.py`, `traces.py`, `metrics.py`, 2 test files | `main.py`, `client.py`, `output.py` |
| 3: Tools | 8 | `tools.py`, 1 test file | `main.py`, `output.py` |
| 4: Copilot | 9-11 | `ask.py`, copilot YAML, 1 test file | `main.py` |

**Total: 11 tasks, ~35 steps, 12 new files, 4 modified files.**
