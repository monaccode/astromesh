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

Write agents as Python decorators, run them locally against the core engine, or run the agent of the same name on a remote node with `connect()`, `remote()` or `.bind()`.

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

## Confirmación y propuestas en local

Las corridas locales usan la misma compuerta que el core.

```python
@tool(description="Paga", requires_approval=True)
async def pagar(monto: int) -> str: ...

@tool(description="Crea un registro", mode="propose")
async def crear(nombre: str) -> str: ...
```

- `requires_approval=True`: la primera vez la tool no se ejecuta; `result.answer` termina con
  `Para confirmar respondé SI. Voy a ejecutar: pagar con monto: 10`. Confirmar es lo mismo que
  en remoto: re-correr en la **misma `session_id`** con `"si"` (o `confirmo`, `dale`, `ok`,
  `listo`). Se ejecuta una vez, y sólo si el modelo repite la llamada con los mismos
  argumentos; cualquier otro mensaje descarta lo pendiente.
- `mode="propose"`: la tool nunca se ejecuta; la llamada sale en `result.propuestas`
  (`tool`, `tipo: "adk"`, `destino` = nombre del agente, `operacion`, `argumentos`) para que
  quien invocó la corrida la apruebe y la ejecute.
- Esto vale para las llamadas que hace el modelo. Una tool llamada desde el código del handler
  (`ctx.call_tool`) se ejecuta tal cual: no pasa por la compuerta ni propone.
- En un equipo o con un agente como tool (`otro.as_tool()`), el "si" lo lee la corrida que
  atiende a la persona, nunca la del miembro o sub-agente (su query la escribió un modelo).
  Éste corre en la misma sesión, su aviso sale en la respuesta de la corrida de arriba, y no
  puede proponer: se le contesta al modelo que no se registró nada.
- **Límite: sub-agentes remotos.** Un agente con `bind()`/`connect()`/`remote()` usado como
  tool corre en el nodo remoto como un turno de persona en la sesión `"default"`: el modelo
  padre puede pasarle `"si"` y satisfacer él solo la compuerta del nodo remoto. La compuerta
  local no protege a los hijos remotos. Las tools de escritura que necesitan aprobación humana
  van en el agente que habla con la persona, o se llama al agente remoto directamente.

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
