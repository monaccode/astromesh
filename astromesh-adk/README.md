# Astromesh ADK

<p align="center">
  <a href="https://monaccode.github.io/astromesh/#ecosystem"><img src="https://img.shields.io/badge/astromesh-author-8b5cf6?labelColor=161b22" alt="Astromesh · Author"></a>
  <a href="https://github.com/monaccode/astromesh/actions/workflows/ci.yml"><img src="https://github.com/monaccode/astromesh/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://github.com/monaccode/astromesh/actions/workflows/release-adk.yml"><img src="https://github.com/monaccode/astromesh/actions/workflows/release-adk.yml/badge.svg" alt="ADK Publish"></a>
  <a href="https://pypi.org/project/astromesh-adk/"><img src="https://img.shields.io/pypi/v/astromesh-adk?label=ADK%20PyPI" alt="ADK PyPI"></a>
  <a href="https://test.pypi.org/project/astromesh-adk/"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Ftest.pypi.org%2Fpypi%2Fastromesh-adk%2Fjson&query=%24.info.version&label=ADK%20TestPyPI" alt="ADK TestPyPI"></a>
  <a href="https://github.com/monaccode/astromesh/blob/develop/LICENSE"><img src="https://img.shields.io/github/license/monaccode/astromesh" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python 3.12+"></a>
</p>

Agent Development Kit for the [Astromesh](https://github.com/monaccode/astromesh) runtime.

Write agents as Python decorators, run them locally against the core engine, or deploy the same code to a remote node.

## Install

```bash
pip install astromesh-adk
```

## Quick start

```python
from astromesh_adk import agent, tool

@tool
def search(query: str) -> str:
    return f"results for {query}"

@agent(name="greeter", model="openai/gpt-4o", tools=[search])
class Greeter:
    system = "You are a helpful assistant."

result = Greeter().run("Hello, what can you search for?")
print(result.answer)
```

## CLI

The ADK ships with a small project CLI:

```bash
astromesh-adk list agents.py
astromesh-adk run agents.py:greeter "Hello"
astromesh-adk chat agents.py:greeter
astromesh-adk check agents.py
astromesh-adk dev agents.py --port 8000 --reload
```

## Documentation

- [ADK Quick Start](../docs/ADK_QUICKSTART.md)
- [ADK Pending Work](../docs/ADK_PENDING.md)
- [Astromesh Docs](https://monaccode.github.io/astromesh/)

## License

Apache-2.0
