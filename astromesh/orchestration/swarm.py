from astromesh.orchestration.patterns import (
    OrchestrationPattern,
    ciclo_de_tools,
    mensajes_de_conversacion,
    presupuesto_de,
)

# Cuántos handoffs lleva la cadena. Viaja en el context de la corrida hija
# (`ToolRegistry.execute`, rama AGENT) y `Agent.run` lo pasa al patrón.
CLAVE_HANDOFFS = "_handoffs"


def handoffs_de(valor) -> int:
    """El contador validado: sólo un entero >= 0 que no sea bool; cualquier otra cosa es 0.

    Llega del context de la corrida, que en `/v1/agents/{name}/run` escribe el llamador.
    """
    if isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0:
        return valor
    return 0


# El pedido del modelo, sin la transcripción: es lo que el destino guarda como turno
# del usuario en su memoria (`ToolRegistry.execute`, rama AGENT). Guardar la
# transcripción la hacía crecer al doble en cada turno con memoria compartida.
CLAVE_PEDIDO = "_pedido"

# Tope de la transcripción que recibe el destino: los turnos más nuevos que entren.
TRANSCRIPCION_MAX_TURNOS = 20
TRANSCRIPCION_MAX_CHARS = 8000


def _transcripcion(context, query=None) -> str:
    """La conversación del agente que delega, más nueva al final y acotada."""
    history = context.get("_history_messages", []) if isinstance(context, dict) else []
    mensajes = [*history, {"role": "user", "content": query}]
    lineas: list[str] = []
    total = 0
    for m in reversed(mensajes):
        contenido = m.get("content")
        if not contenido or not isinstance(contenido, str):
            continue
        linea = f"{m.get('role')}: {contenido}"
        if len(lineas) >= TRANSCRIPCION_MAX_TURNOS or total + len(linea) > TRANSCRIPCION_MAX_CHARS:
            break
        lineas.append(linea)
        total += len(linea) + 1
    return "\n".join(reversed(lineas))


class SwarmPattern(OrchestrationPattern):
    """Pasa el control a otro agente: su respuesta es la final, no vuelve acá.

    Los agentes destino son las tools `type: agent` del manifiesto (las arma
    `AgentRuntime._build_pattern`). El destino recibe la conversación (acotada) en
    `query`, y guarda en su memoria sólo el pedido. Con `max_handoffs` encadenados ya no se ofrecen ni se ejecutan.
    """

    consumes_turn_context = True

    def __init__(self, workers: list[str], max_handoffs: int = 3):
        self._workers = list(workers)
        self._max_handoffs = max_handoffs

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        n = handoffs_de(context.get(CLAVE_HANDOFFS) if isinstance(context, dict) else None)
        activos = set(self._workers) if n < self._max_handoffs else set()
        bloqueados = set(self._workers) - activos
        ofrecidas = [t for t in tools if t.get("function", {}).get("name") not in bloqueados]

        async def tool_con_handoff(name, args):
            if name in bloqueados:
                return f"La tool «{name}» no está disponible para este agente."
            if name not in activos:
                return await tool_fn(name, args)
            historia = _transcripcion(context, query)
            crudo = args.get("query", "")
            pedido = f"Pedido: {crudo}"
            return await tool_fn(
                name,
                {
                    **args,
                    "query": f"{historia}\n\n{pedido}" if historia else pedido,
                    CLAVE_PEDIDO: crudo if isinstance(crudo, str) else str(crudo),
                    CLAVE_HANDOFFS: n + 1,
                },
            )

        return await ciclo_de_tools(
            mensajes_de_conversacion(query, context),
            model_fn,
            tool_con_handoff,
            ofrecidas,
            max_iterations,
            role="reasoner",
            presupuesto=presupuesto_de(context),
            finales=activos,
        )
