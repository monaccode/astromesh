"""Convención de nombres de las cadenas compiladas.

Vive aparte de `compiler.py`, y sin un solo import, para romper un ciclo real:
`chain.compiler` importa `workflow.models`, lo que ejecuta `workflow/__init__`,
que importa `workflow.loader`, que necesita el prefijo reservado. Si el prefijo
viviera en `compiler.py`, ese último import encontraría el módulo a medio
inicializar y `from astromesh.runtime.engine import AgentRuntime` reventaría con
un ImportError — que es exactamente lo que pasó al publicar v0.38.0.
"""

CHAIN_PREFIX = "__chain__"


def chain_workflow_name(agent_name: str) -> str:
    """Nombre del workflow sintético que compila la cadena de un agente."""
    return f"{CHAIN_PREFIX}{agent_name}"
