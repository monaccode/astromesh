from astromesh.orchestration.patterns import (
    OrchestrationPattern,
    ciclo_de_tools,
    mensajes_de_conversacion,
    presupuesto_de,
)


class SupervisorPattern(OrchestrationPattern):
    """Un coordinador que SÓLO delega en sus trabajadores y contesta con lo que juntó.

    Los trabajadores son las tools `type: agent` del manifiesto (las arma
    `AgentRuntime._build_pattern`): se le ofrecen sólo ésas al modelo, como tools
    nativas, y una llamada a cualquier otra no se ejecuta.
    """

    consumes_turn_context = True

    def __init__(self, workers: list[str] | None = None):
        self._workers = list(workers or [])

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        permitidas = set(self._workers)
        ofrecidas = [t for t in tools if t.get("function", {}).get("name") in permitidas]
        return await ciclo_de_tools(
            mensajes_de_conversacion(query, context),
            model_fn,
            tool_fn,
            ofrecidas,
            max_iterations,
            role="supervisor",
            permitidas=permitidas,
            presupuesto=presupuesto_de(context),
        )
