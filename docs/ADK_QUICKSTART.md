# Astromesh ADK — Quick Start

## Installation

```bash
pip install astromesh-adk
```

## Define an Agent

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

## Run It

```python
import asyncio

async def main():
    result = await math_assistant.run("What is 5 + 3?")
    print(result.answer)

asyncio.run(main())
```

## CLI

```bash
# Run from command line
astromesh-adk run my_agents.py:math_assistant "What is 5 + 3?"

# Interactive chat
astromesh-adk chat my_agents.py:math_assistant

# Dev server with playground
astromesh-adk dev my_agents.py

# List all agents
astromesh-adk list my_agents.py

# Validate configuration
astromesh-adk check my_agents.py
```

## Connect to Astromesh Remote

```python
from astromesh_adk import connect

connect(url="https://my-cluster.astromesh.io", api_key="ask-xxx")

# Same code, now runs on remote Astromesh
result = await math_assistant.run("What is 5 + 3?")
```

## Next Steps

- See `astromesh-adk/examples/` for more patterns
- Read the full spec at `docs/superpowers/specs/2026-03-17-astromesh-adk-design.md`
