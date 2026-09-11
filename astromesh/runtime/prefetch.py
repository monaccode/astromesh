"""`spec.prefetch`: búsquedas de solo lectura que corren antes del LLM.

Un turno que siempre empieza buscando lo mismo (quién escribe, qué está
pendiente) gasta un viaje al LLM por búsqueda sólo para decidir hacerla, y la
búsqueda en sí cuesta milisegundos. Este bloque las corre antes y deja el
resultado en la variable `prefetch` del prompt.

Sólo lecturas: una acción de integración con `request.method: GET` que no esté
en `confirm`. Una declaración inválida NO carga el agente —a diferencia del
resto del spec, que avisa y sigue—: un prefetch salteado en silencio deja al
modelo sin los datos, y el síntoma sería negarle el acceso a alguien que sí está.
"""

from astromesh.core.tools import ToolType
from astromesh.errors import AgentConfigError


def validar_prefetch(agente, declarado, tools):
    """Las entradas normalizadas de `spec.prefetch`, o `[]` si no hay bloque."""
    if declarado is None:
        return []
    if not isinstance(declarado, list):
        raise AgentConfigError(f"agent {agente!r}: spec.prefetch tiene que ser una lista")

    vistos = set()
    entradas = []
    for i, entrada in enumerate(declarado):
        donde = f"agent {agente!r}: spec.prefetch[{i}]"
        if not isinstance(entrada, dict):
            raise AgentConfigError(f"{donde} tiene que ser un objeto")
        nombre = entrada.get("name")
        if not isinstance(nombre, str) or not nombre:
            raise AgentConfigError(f"{donde} no tiene `name`")
        if nombre in vistos:
            raise AgentConfigError(f"{donde} repite el name {nombre!r}")
        vistos.add(nombre)

        tool = entrada.get("tool")
        definicion = tools.get(tool) if isinstance(tool, str) else None
        if definicion is None:
            raise AgentConfigError(
                f"{donde} ({nombre!r}) usa la tool {tool!r}, que el agente no tiene registrada"
            )
        if definicion.tool_type != ToolType.INTEGRATION:
            raise AgentConfigError(
                f"{donde} ({nombre!r}): {tool!r} no es una acción de integración"
            )
        accion = (definicion.integration_config or {}).get("action_spec")
        metodo = getattr(getattr(accion, "request", None), "method", None)
        if metodo != "GET":
            raise AgentConfigError(
                f"{donde} ({nombre!r}): {tool!r} es {metodo}; prefetch sólo corre lecturas (GET)"
            )
        if definicion.needs_confirmation:
            raise AgentConfigError(f"{donde} ({nombre!r}): {tool!r} está en confirm")

        argumentos = entrada.get("arguments") or {}
        if not isinstance(argumentos, dict):
            raise AgentConfigError(f"{donde} ({nombre!r}): `arguments` tiene que ser un objeto")
        when = entrada.get("when")
        if when is not None and not isinstance(when, str):
            raise AgentConfigError(f"{donde} ({nombre!r}): `when` tiene que ser un string")

        entradas.append({"name": nombre, "tool": tool, "arguments": argumentos, "when": when})
    return entradas
