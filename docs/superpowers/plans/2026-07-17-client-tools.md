# Client Tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `type: client` — a tool the runtime announces to the model and does not execute — so an agent can drive a client's interface; and make the YAML tool loader stop discarding unsupported types in silence.

**Architecture:** Three small additions mirroring what's already there: a `ToolType.CLIENT` enum member, a `register_client_tool()` modeled on `register_agent_tool()`, and a branch in the YAML loader beside `builtin`/`agent`. `execute()` returns `{"ok": True}` without running anything. The call reaches consumers through the two paths that already exist: `on_event` live (0.34.0) and `AgentRunResponse.steps` after the fact.

**Tech Stack:** Python 3.12, pytest (`asyncio_mode = "auto"`), uv.

**Spec:** `docs/superpowers/specs/2026-07-17-client-tools-design.md`

## Global Constraints

- **Nothing that works today may break.** `builtin` and `agent` tools, the `execute()` chain, and every existing YAML must behave exactly as before. The full suite (799 passed / 18 pre-existing skips) must stay green with no existing test modified — except the two agent YAMLs this plan deliberately fixes (Task 4).
- **An unsupported `type` WARNs, it does not raise.** Raising would stop `bootstrap()` from starting the runtime at all, and would take down anyone who upgrades with `internal` in a YAML — for tools that already did nothing. The error is promised for 1.0, not now.
- **`execute()` on a `client` tool returns `{"ok": True}`** — not the arguments (the model wrote them; `steps.action_input` already carries them) and not a delivery claim (the runtime signals; it cannot know whether anyone listened).
- **A `client` tool must appear in `get_tool_schemas()`** or the model never sees it and the feature does not exist.
- Python 3.12. Tests: `uv run pytest -v` from the repo root. `asyncio_mode = "auto"` — do NOT add `@pytest.mark.asyncio`. Tests live flat in `tests/`.
- CI runs `uv run ruff check astromesh/ tests/` **and** `uv run ruff format --check astromesh/ tests/`. Run both before committing — the format check has failed a branch in this repo before.
- Commits in Spanish, conventional format.

## File Structure

| File | Responsibility |
|---|---|
| `astromesh/core/tools.py` | **Modify.** `ToolType.CLIENT`, `register_client_tool()`, the `execute()` branch |
| `astromesh/runtime/engine.py` | **Modify.** The loader's `client` branch + the WARNING for unsupported types |
| `config/agents/sales-qualifier.agent.yaml` | **Modify.** `internal` → `client` |
| `config/agents/autolink-parts.agent.yaml` | **Modify.** `internal` → `client` |
| `docs/CONFIGURATION_GUIDE.md` | **Modify.** Line ~123's tool-type list currently lists four types, none of which work |
| `tests/test_client_tools.py` | **Create.** |

---

## Task 1: `ToolType.CLIENT`, `register_client_tool`, and the `execute()` branch

**Files:**
- Modify: `astromesh/core/tools.py` — `ToolType` (~line 19), a new method after `register_agent_tool` (~line 113), the `execute()` chain (~line 120)
- Test: `tests/test_client_tools.py`

**Interfaces:**
- Produces:
  ```python
  ToolType.CLIENT  # "client"
  ToolRegistry.register_client_tool(name: str, description: str, parameters: dict | None = None, **kwargs) -> None
  # ToolRegistry.execute(name, args, context) on a CLIENT tool -> {"ok": True}
  ```

**Context:** `ToolRegistry` (in `astromesh/core/tools.py`) holds `ToolDefinition` dataclasses in `self._tools`, and `get_tool_schemas()` (line ~164) turns every registered tool into the JSON the model sees. Every existing tool type assumes the *runtime* does the work: `INTERNAL` runs a Python handler, `AGENT` delegates to another agent, `MCP_*` calls a server. `CLIENT` is the first where the work belongs to whoever is listening.

`register_agent_tool` (line 84) is the shape to mirror: it builds a `ToolDefinition` with a `tool_type`, a `parameters` default, and `**kwargs` passthrough — no handler.

`ToolDefinition`'s fields are `name`, `description`, `tool_type`, `parameters`, `handler=None`, `mcp_config`, `requires_approval`, `timeout_seconds`, `rate_limit`, `permissions`, `agent_config`, `context_transform`. A client tool needs only the first four.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_tools.py
"""Client tools: the runtime announces them to the model and does not execute them."""

from __future__ import annotations

from astromesh.core.tools import ToolRegistry, ToolType


PARAMS = {
    "type": "object",
    "properties": {"label": {"type": "string", "description": "What to show"}},
    "required": ["label"],
}


def test_register_client_tool_records_it_as_client():
    tools = ToolRegistry()
    tools.register_client_tool(
        name="show_thing", description="Show a thing", parameters=PARAMS
    )
    tool = tools._tools["show_thing"]
    assert tool.tool_type == ToolType.CLIENT
    assert tool.handler is None
    assert tool.parameters == PARAMS


def test_a_client_tool_is_offered_to_the_model():
    """If it isn't in the schemas the model never sees it and the feature doesn't exist."""
    tools = ToolRegistry()
    tools.register_client_tool(
        name="show_thing", description="Show a thing", parameters=PARAMS
    )
    schemas = tools.get_tool_schemas()
    fn = next(s["function"] for s in schemas if s["function"]["name"] == "show_thing")
    assert fn["description"] == "Show a thing"
    assert fn["parameters"] == PARAMS


async def test_executing_a_client_tool_returns_ok_and_runs_nothing():
    tools = ToolRegistry()
    tools.register_client_tool(
        name="show_thing", description="Show a thing", parameters=PARAMS
    )
    result = await tools.execute("show_thing", {"label": "hola"})
    assert result == {"ok": True}


async def test_a_client_tool_does_not_echo_its_arguments():
    """The model wrote the args; steps.action_input already carries them."""
    tools = ToolRegistry()
    tools.register_client_tool(name="show_thing", description="d", parameters=PARAMS)
    result = await tools.execute("show_thing", {"label": "secreto"})
    assert "secreto" not in str(result)


async def test_a_client_tool_does_not_claim_delivery():
    """The runtime signals; it cannot know whether anyone listened."""
    tools = ToolRegistry()
    tools.register_client_tool(name="show_thing", description="d", parameters=PARAMS)
    result = await tools.execute("show_thing", {"label": "hola"})
    assert "delivered" not in result and "sent" not in result


def test_register_client_tool_defaults_its_parameters():
    tools = ToolRegistry()
    tools.register_client_tool(name="ping", description="d")
    assert tools._tools["ping"].parameters["type"] == "object"


async def test_an_unknown_tool_still_reports_not_found():
    """The pre-existing behavior for a name nobody registered."""
    tools = ToolRegistry()
    result = await tools.execute("nope", {})
    assert "error" in result
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_client_tools.py -v`
Expected: FAIL — `AttributeError: CLIENT` on the import, or `ToolRegistry` has no `register_client_tool`.

- [ ] **Step 3: Add the enum member**

In `astromesh/core/tools.py`, add to `ToolType` (after `INTERNAL = "internal"`):

```python
    CLIENT = "client"
```

- [ ] **Step 4: Add `register_client_tool`**

In `astromesh/core/tools.py`, immediately after `register_agent_tool`'s body ends (~line 113), add:

```python
    def register_client_tool(
        self,
        name: str,
        description: str,
        parameters: dict | None = None,
        **kwargs,
    ):
        """Register a tool the runtime announces but does not execute.

        The call itself is the product: it reaches consumers live through
        AgentRuntime.run's on_event ({"type": "tool_call", ...}) and afterwards
        through AgentRunResponse.steps (action / action_input). What the call
        means is the consumer's business, not the runtime's — which is why this
        is 'client' and not 'ui'.

        With nobody listening, a client tool is a silent no-op. That is correct:
        the runtime's job is to announce it and record the call.
        """
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            tool_type=ToolType.CLIENT,
            parameters=parameters or {"type": "object", "properties": {}},
            **kwargs,
        )
```

- [ ] **Step 5: Add the `execute()` branch**

In `astromesh/core/tools.py`'s `execute()`, add a branch to the chain. Put it immediately after the `if tool.tool_type == ToolType.INTERNAL and tool.handler:` branch and before the `elif tool.tool_type.value.startswith("mcp_"):` one:

```python
        elif tool.tool_type == ToolType.CLIENT:
            # Announced, not executed. {"ok": True} is the only honest answer:
            # ReAct needs an observation to continue, the model already wrote the
            # arguments, and the runtime cannot know whether a consumer listened.
            return {"ok": True}
```

- [ ] **Step 6: Run the test and watch it pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_client_tools.py -v`
Expected: PASS (7 tests).

- [ ] **Step 7: Verify nothing else regressed**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest -v`
Expected: PASS (799 passed / 18 skipped). A new enum member and a new branch must not touch any existing path.

- [ ] **Step 8: Lint, format, commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
uv run ruff check astromesh/ tests/
uv run ruff format --check astromesh/ tests/
git add astromesh/core/tools.py tests/test_client_tools.py
git commit -m "feat(tools): tipo client — tools que el runtime anuncia y no ejecuta"
```

---

## Task 2: The YAML loader's `client` branch, and the end of the silent ignore

**Files:**
- Modify: `astromesh/runtime/engine.py:375-400` (the `for tool_def in spec.get("tools", [])` loop)
- Test: `tests/test_client_tools.py` (append)

**Interfaces:**
- Consumes: `register_client_tool(name, description, parameters=None, **kwargs)` from Task 1

**Context:** This is the bug that motivated the whole change. The loop reads `tool_type = tool_def.get("type", "internal")` (line 376) and then handles exactly two cases: `builtin` and `agent`. **Everything else falls off the end of the `if/elif` and is discarded without a word** — no registration, no schema, no log. Since `internal` is the *default*, a tool with no `type` doesn't exist either.

Two agents in this very repo have phantom tools because of it (Task 4 fixes them).

The WARNING must name the tool, the agent and the type — a message that doesn't say *which* tool in *which* agent sends the reader back into the same search that cost us the time in the first place. `metadata["name"]` is in scope in `_build_agent` (it's used at line 380).

**It must not raise.** Raising would take `bootstrap()` down for the two repo agents and for anyone upgrading with `internal` in a YAML — over tools that already did nothing. The error is promised for 1.0.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_client_tools.py`:

```python
import logging

import pytest

from astromesh.runtime.engine import AgentRuntime


def _agent_spec(tools: list[dict]) -> dict:
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "test-agent", "version": "1.0.0"},
        "spec": {
            "identity": {"display_name": "Test", "description": "d"},
            "model": {
                "primary": {
                    "provider": "openai_compat",
                    "model": "gpt-4o-mini",
                    "endpoint": "https://example.invalid/v1",
                    "api_key_env": "NOPE_KEY",
                }
            },
            "prompts": {"system": "you are a test agent"},
            "orchestration": {"pattern": "react", "max_iterations": 3},
            "tools": tools,
        },
    }


def test_a_client_tool_declared_in_yaml_is_actually_registered():
    """The bug this whole change exists for: the loader used to discard it silently."""
    runtime = AgentRuntime(config_dir="/nonexistent")
    agent = runtime._build_agent(
        _agent_spec(
            [
                {
                    "name": "diagram_process",
                    "type": "client",
                    "description": "Draw the process",
                    "parameters": {
                        "type": "object",
                        "properties": {"nodes": {"type": "array"}},
                    },
                }
            ]
        )
    )
    names = [s["function"]["name"] for s in agent._tools.get_tool_schemas()]
    assert "diagram_process" in names


def test_an_unsupported_tool_type_warns_and_names_what_it_dropped(caplog):
    with caplog.at_level(logging.WARNING):
        runtime = AgentRuntime(config_dir="/nonexistent")
        runtime._build_agent(
            _agent_spec([{"name": "lookup_company", "type": "internal", "description": "d"}])
        )
    assert "lookup_company" in caplog.text
    assert "test-agent" in caplog.text
    assert "internal" in caplog.text


def test_an_unsupported_tool_type_does_not_stop_the_agent_from_loading():
    """Raising would take bootstrap() down for every existing YAML with 'internal'."""
    runtime = AgentRuntime(config_dir="/nonexistent")
    agent = runtime._build_agent(
        _agent_spec([{"name": "ghost", "type": "internal", "description": "d"}])
    )
    assert agent is not None
    assert "ghost" not in [s["function"]["name"] for s in agent._tools.get_tool_schemas()]


def test_a_tool_with_no_type_at_all_warns(caplog):
    """'internal' is the default, so a tool with no type silently didn't exist."""
    with caplog.at_level(logging.WARNING):
        runtime = AgentRuntime(config_dir="/nonexistent")
        runtime._build_agent(_agent_spec([{"name": "typeless", "description": "d"}]))
    assert "typeless" in caplog.text
```

**Note for the implementer:** `_build_agent(self, config)` is **synchronous** and takes the *whole* YAML dict (it reads `config["metadata"]` and `config["spec"]` itself) — that's why these four tests are plain `def`, not `async def`. What else it needs from that dict may differ from the sketch above — read `astromesh/runtime/engine.py:363-400` and adjust `_agent_spec` to whatever it actually requires (memory, RAG and provider blocks may need stubbing or may be optional). **Adjust the test, never the production code, to make the fixture load.** If `_build_agent` insists on reaching a real provider, use `monkeypatch` rather than weakening the assertion.

- [ ] **Step 2: Run the tests and watch them fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_client_tools.py -v -k "yaml or unsupported or no_type"`
Expected: FAIL — `diagram_process` is not in the schemas (the loader drops it), and nothing is logged.

- [ ] **Step 3: Add the `client` branch and the warning**

In `astromesh/runtime/engine.py`, in the `for tool_def in spec.get("tools", []):` loop (~line 375), add a branch after the `elif tool_type == "agent":` block, and an `else` that warns:

```python
            elif tool_type == "client":
                tools.register_client_tool(
                    name=tool_def["name"],
                    description=tool_def.get("description", ""),
                    parameters=tool_def.get("parameters"),
                    rate_limit=tool_def.get("rate_limit"),
                )
            else:
                # Until 0.35.0 this fell off the end of the chain in silence: the tool
                # was never registered, never reached the model, and nothing said so —
                # you got an agent with no tools and nothing to look at. 'internal' is
                # the default type, so a tool with no 'type' landed here too.
                # It warns rather than raises: raising would stop bootstrap() for every
                # existing YAML that declares one. The error comes in 1.0.
                logger.warning(
                    "agent %r declares tool %r with unsupported type %r — ignoring it. "
                    "YAML supports: builtin, agent, client.",
                    metadata["name"],
                    tool_def.get("name"),
                    tool_type,
                )
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_client_tools.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Verify nothing else regressed**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest -v`
Expected: PASS (799 / 18 skipped). Note the two repo agents with `internal` tools will now log warnings during any test that loads them — that's the point, and it must not fail anything.

- [ ] **Step 6: Lint, format, commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
uv run ruff check astromesh/ tests/
uv run ruff format --check astromesh/ tests/
git add astromesh/runtime/engine.py tests/test_client_tools.py
git commit -m "fix(runtime): cargar tools client desde YAML y avisar en vez de ignorar en silencio"
```

---

## Task 3: The composition with `on_event`

**Files:**
- Test: `tests/test_client_tools.py` (append)

**Interfaces:**
- Consumes: everything from Tasks 1 and 2, plus `AgentRuntime.run(..., on_event=...)` from 0.34.0

**Context:** Tasks 1 and 2 make a client tool registrable and callable. This task pins the thing that makes it *useful*, and it's the only test that proves the feature end to end.

A client tool's call reaches a consumer by two paths, and both must hold:
- **Live**, via `on_event` → `{"type": "tool_call", "id", "name", "arguments"}`
- **After the fact**, in the run's result → `steps` with `action` and `action_input`

If only the first held, a REST consumer couldn't use client tools. If only the second, the live UI this was built for wouldn't work. Nothing today tests the two together.

No production code changes in this task. If a test here fails, the bug is in Task 1 or 2.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_client_tools.py`:

```python
from unittest.mock import AsyncMock, MagicMock

from astromesh.runtime.engine import Agent


class _FakeResponse:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.model = "fake-model"
        self.provider = "fake"
        self.latency_ms = 1
        self.cost = 0.0
        self.usage = {"input_tokens": 1, "output_tokens": 1}


class _CallsTheClientTool:
    """Stands in for a real pattern: drives the same closures every pattern drives."""

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        from astromesh.orchestration.patterns import AgentStep

        observation = await tool_fn("diagram_process", {"nodes": [{"id": "a"}]})
        return {
            "answer": "listo",
            "steps": [
                AgentStep(
                    action="diagram_process",
                    action_input={"nodes": [{"id": "a"}]},
                    observation=str(observation),
                )
            ],
        }


async def test_a_client_tool_reaches_a_consumer_live_and_in_steps():
    """The two paths of the contract. Neither alone is enough."""
    agent = Agent.__new__(Agent)
    agent.name = "test-agent"
    agent._pattern = _CallsTheClientTool()
    agent._role_map = {}
    agent._orchestration_config = {"pattern": "test"}
    agent._permissions = {}
    agent._guardrails = {}
    agent._rag = None
    agent._knowledge = None

    router = MagicMock()
    router.route = AsyncMock(return_value=_FakeResponse(content="narrando"))
    agent._routers = {"default": router}

    tools = ToolRegistry()
    tools.register_client_tool(
        name="diagram_process",
        description="Draw the process",
        parameters={"type": "object", "properties": {"nodes": {"type": "array"}}},
    )
    agent._tools = tools

    memory = MagicMock()
    memory.build_context = AsyncMock(return_value=[])
    memory.persist_turn = AsyncMock()
    agent._memory = memory

    prompt = MagicMock()
    prompt.render = MagicMock(return_value="you are a test agent")
    agent._prompt_engine = prompt

    events = []
    result = await agent.run("hola", "s1", on_event=events.append)

    # Path 1: live.
    call = next(e for e in events if e["type"] == "tool_call")
    assert call["name"] == "diagram_process"
    assert call["arguments"] == {"nodes": [{"id": "a"}]}
    assert next(e for e in events if e["type"] == "tool_result")["ok"] is True

    # Path 2: after the fact.
    step = result["steps"][0]
    assert step.action == "diagram_process"
    assert step.action_input == {"nodes": [{"id": "a"}]}
```

**Note for the implementer:** the `Agent.__new__` + stub-the-collaborators shape is the one `tests/test_run_events.py` already uses — read it and mirror it, including any attribute it stubs that this sketch misses. The collaborator method names there (`build_context`, `persist_turn`) are the real ones; a previous plan got them wrong. **Adjust the test to the code, not the code to the test.**

- [ ] **Step 2: Run the test**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_client_tools.py -v -k "live_and_in_steps"`
Expected: PASS on the first run — Tasks 1 and 2 already made it work. **If it fails, do not adjust it until you've checked whether it found a real gap in Task 1 or 2.** That's what it's for.

- [ ] **Step 3: Commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
uv run ruff format --check astromesh/ tests/
git add tests/test_client_tools.py
git commit -m "test(tools): fijar los dos caminos de una tool client — on_event y steps"
```

---

## Task 4: The repo's own lying agents, and the lying docs

**Files:**
- Modify: `config/agents/sales-qualifier.agent.yaml`
- Modify: `config/agents/autolink-parts.agent.yaml`
- Modify: `docs/CONFIGURATION_GUIDE.md` (~line 123)
- Test: `tests/test_client_tools.py` (append)

**Context:** Two agents shipped in this repo declare tools that don't exist:
- `sales-qualifier.agent.yaml` → `lookup_company`, `type: internal`
- `autolink-parts.agent.yaml` → two `internal` tools

They load, the model never sees those tools, nobody is told. After Task 2 they'll at least warn — but they're still wrong. `type: internal` in a YAML can only ever have meant `client`: a YAML cannot supply a Python handler.

This isn't free cleanup. `sales-qualifier` is the agent the WebSocket smoke test drives, and an example agent that lies about its tools is debt this project already paid for once.

And the guide is worse than the code. `docs/CONFIGURATION_GUIDE.md:123` reads:

```yaml
      type: internal            # internal | mcp | webhook | rag
```

**All four are false** — none load from YAML. The two that do work, `builtin` and `agent`, aren't in that list. `webhook` and `rag` exist in `ToolType` but no loader branch and (for `webhook`) not even an `execute()` branch.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_client_tools.py`:

```python
import pathlib

import yaml


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _agent_files():
    return sorted((REPO_ROOT / "config" / "agents").glob("*.agent.yaml"))


def test_no_shipped_agent_declares_a_tool_type_the_loader_drops():
    """A shipped example that lies about its tools teaches the lie."""
    supported = {"builtin", "agent", "client"}
    offenders = []
    for path in _agent_files():
        spec = yaml.safe_load(path.read_text())
        for tool in (spec.get("spec") or {}).get("tools", []) or []:
            tool_type = tool.get("type", "internal")
            if tool_type not in supported:
                offenders.append(f"{path.name}:{tool.get('name')} -> {tool_type}")
    assert offenders == []


def test_the_configuration_guide_lists_the_types_that_actually_load():
    guide = (REPO_ROOT / "docs" / "CONFIGURATION_GUIDE.md").read_text()
    assert "builtin | agent | client" in guide
    assert "# internal | mcp | webhook | rag" not in guide
```

- [ ] **Step 2: Run and watch it fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_client_tools.py -v -k "shipped_agent or configuration_guide"`
Expected: FAIL — the offenders list names the three phantom tools; the guide still carries the old comment.

- [ ] **Step 3: Fix the two agents**

In `config/agents/sales-qualifier.agent.yaml` and `config/agents/autolink-parts.agent.yaml`, change each tool's `type: internal` to `type: client`. Change **nothing else** — not the names, not the descriptions, not the parameters. These tools were never executed, so nothing about their behavior changes: they go from silently absent to announced.

- [ ] **Step 4: Fix the guide**

In `docs/CONFIGURATION_GUIDE.md` (~line 123), replace:

```yaml
      type: internal            # internal | mcp | webhook | rag
```

with:

```yaml
      type: builtin             # builtin | agent | client
```

And immediately after that tools block, add:

```markdown
> **Tool types loadable from YAML:** `builtin` (a tool shipped with the runtime),
> `agent` (another agent, callable as a tool), and `client` (announced to the model,
> executed by whoever is listening — the call arrives live via `on_event` and
> afterwards in `steps`; with nobody listening it is a no-op).
>
> `webhook` and `rag` appear in `ToolType` but are **not** declarable from YAML.
> `internal` is deprecated: a YAML cannot supply a Python handler, so what it meant
> is now `client`. Declaring an unsupported type logs a warning and skips the tool;
> from 1.0 it will be an error.
```

- [ ] **Step 5: Run and watch them pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_client_tools.py -v`
Expected: PASS (14 tests).

- [ ] **Step 6: Verify the whole suite**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest -v`
Expected: PASS (799 / 18 skipped). Any test that loads those two agents now gets three real tools where it got none — if one fails, it was asserting on the broken state and that's worth reading carefully before touching it.

- [ ] **Step 7: Lint, format, commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
uv run ruff check astromesh/ tests/
uv run ruff format --check astromesh/ tests/
git add config/agents/ docs/CONFIGURATION_GUIDE.md tests/test_client_tools.py
git commit -m "fix(config): los agentes de ejemplo declaraban tools fantasma; la guía las documentaba mal"
```

---

## Notes for whoever executes this

**The consumer is already written.** `fainansu-agents` (spec: `2026-07-17-marketing-agent-design.md` in that repo) declares six client tools — `diagram_process`, `estimate_cost`, `detect_bottleneck`, `compute_savings`, `show_ecosystem`, `book_meeting` — and the web that renders them is live at fainansu.tech running on a local mock. It cannot be implemented until this ships. That's why this is small and separate rather than folded in there.

**What this does not do:** `webhook` and `rag` stay undeclarable from YAML — features nobody asked for. Third-party tool packages stay impossible (`auto_discover()` imports a hardcoded `ALL_TOOLS`). The warning stays a warning until 1.0. The ADK doesn't inherit any of this: it duplicates the runtime rather than calling it, which is the same debt that keeps it from emitting events.
