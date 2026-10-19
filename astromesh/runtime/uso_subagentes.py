"""El uso de los sub-agentes (tools `type: agent`) de un run raíz.

Un acumulador por run raíz: lo crea el `Agent.run` que no recibe uno y viaja
hacia abajo por el `context` de `tool_fn` (clave `CLAVE_USO_SUBAGENTES`) y la
rama AGENT de `ToolRegistry.execute`. No es global: dos runs concurrentes tienen
cada uno el suyo.

Cada sub-agente, al terminar (bien, bloqueado o con error: se registra en el
`finally` de `Agent.run`), deja acá el dict de SU trace — sólo sus spans, sin
los de sus propios hijos, que se registran solos. Así la lista es plana y nada
se cuenta dos veces. El run raíz la expone como `trace["subagentes"]`, y
`usage_from_trace` suma esos spans: el `usage` / `usage.by_model` que leen REST,
el `done` del WS y Nexus incluye a los sub-agentes a cualquier profundidad.

`linaje` son los `run_id` de los ancestros de cada registro: un run intermedio
cuenta para su `cost_limit` sólo lo que gastó SU subárbol, aunque un hermano
esté corriendo en paralelo bajo el mismo raíz.
"""

from collections.abc import Callable

CLAVE_USO_SUBAGENTES = "_uso_subagentes"


class UsoSubagentes:
    def __init__(self) -> None:
        self.trazas: list[dict] = []
        self._linajes: list[tuple[str, ...]] = []

    def registrar(self, linaje: tuple[str, ...], traza: dict) -> None:
        self.trazas.append(traza)
        self._linajes.append(linaje)

    def tokens_bajo(self, run_id: str, tokens_of: Callable[[dict], int]) -> int:
        """Tokens de las llamadas al modelo de los descendientes de `run_id`,
        contados con la regla del que pregunta (`GuardrailsEngine.tokens_of`)."""
        total = 0
        for linaje, traza in zip(self._linajes, self.trazas, strict=True):
            if run_id not in linaje:
                continue
            for span in traza.get("spans", []):
                attrs = span.get("attributes", {}) if isinstance(span, dict) else {}
                if not isinstance(attrs, dict) or "input_tokens" not in attrs:
                    continue
                total += tokens_of(
                    {
                        "input_tokens": attrs.get("input_tokens", 0),
                        "output_tokens": attrs.get("output_tokens", 0),
                    }
                )
        return total
