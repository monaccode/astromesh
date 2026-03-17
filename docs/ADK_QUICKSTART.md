# Astromesh ADK — Quick Start

The Astromesh ADK lets you define agents directly in Python (decorators or classes), run them locally, and later switch to remote execution on an Astromesh cluster with minimal code changes.

---

## What you get with ADK

- Python-first agent definitions (`@agent`, class-based agents)
- Typed tools (`@tool`) with schema generation
- Async execution with a consistent `RunResult`
- CLI for run/chat/dev/list/check workflows
- Optional remote execution through Astromesh API

---

## Installation

```bash
pip install astromesh-adk
```

Recommended: use a virtual environment and Python 3.12+.

---

## Minimal agent example

Create `my_agents.py`:

```python
from astromesh_adk import agent, tool

@tool(description="Add two numbers")
async def add(a: int, b: int) -> int:
    return a + b

@agent(
    name="math-assistant",
    model="ollama/llama3",
    tools=[add],
)
async def math_assistant(ctx):
    """You are a math assistant. Use the add tool for calculations."""
    return None
```

In this pattern, your agent function mainly defines behavior and instructions. Returning `None` allows the runtime orchestration to handle model/tool loops.

---

## Run from Python

```python
import asyncio
from my_agents import math_assistant

async def main():
    result = await math_assistant.run("What is 5 + 3?")
    print(result.answer)

asyncio.run(main())
```

You typically consume:
- `result.answer` for final text output
- trace/metadata fields for observability (depending on runtime configuration)

---

## Run from CLI

```bash
# One-shot run
astromesh-adk run my_agents.py:math_assistant "What is 5 + 3?"

# Interactive chat loop
astromesh-adk chat my_agents.py:math_assistant

# Development server / playground
astromesh-adk dev my_agents.py

# Discover agents in file
astromesh-adk list my_agents.py

# Validate config and declarations
astromesh-adk check my_agents.py
```

Use `dev` when iterating quickly on prompts, tools, and model settings.

---

## Switch to remote execution

```python
from astromesh_adk import connect
from my_agents import math_assistant

connect(url="https://my-cluster.astromesh.io", api_key="ask-xxx")

# Same call site; execution routed to remote Astromesh
result = await math_assistant.run("What is 5 + 3?")
```

This enables local development with remote production execution without rewriting your agent interface.

---

## Recommended project layout

```text
project/
  my_agents.py
  tools/
    math_tools.py
  tests/
    test_agents.py
```

As your codebase grows, split tools and agent definitions into modules and keep tests close to agent behavior.

---

## Release the package (automatic)

`astromesh-adk` is published automatically using the workflow:
`/.github/workflows/release-adk.yml`

Release flow:
- Push tag `adk-vX.Y.Z`
- Validate tag version vs `astromesh-adk/pyproject.toml`
- Build wheel + sdist
- Publish to TestPyPI
- Run smoke test (`pip install` + import + CLI help)
- Publish to PyPI

### One-time prerequisites

1. Create the `astromesh-adk` project in TestPyPI and PyPI.
2. Ensure `astromesh` is also published to PyPI/TestPyPI (ADK depends on it).
3. Configure Trusted Publishing (OIDC) in both registries:
   - Repository: this GitHub repo
   - Workflow: `release-adk.yml`
   - Allowed trigger: tags `adk-v*`
4. Ensure GitHub Environments exist (used by workflow):
   - `testpypi`
   - `pypi`

### Release command

```bash
git tag adk-v0.1.0
git push origin adk-v0.1.0
```

Before tagging, update both:
- `astromesh-adk/pyproject.toml` -> `project.version`
- `astromesh-adk/astromesh_adk/__init__.py` -> `__version__`

If versions do not match, the workflow fails intentionally.

---

## Next steps

- Explore `astromesh-adk/examples/` for advanced patterns
- Read `docs/ADK_PENDING.md` for current implementation status
- Review full design spec: `docs/superpowers/specs/2026-03-17-astromesh-adk-design.md`
