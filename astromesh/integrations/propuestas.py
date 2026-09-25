"""Tools que proponen una escritura en vez de ejecutarla (`mode: propose`).

Una operación `api` o una tool `mcp` con `writes: true` sólo carga con
`mode: propose` (`integrations/api.py`, `integrations/mcp.py`). Su handler no
llama a nadie: valida los argumentos contra el schema que ve el modelo, los
anota en la lista de propuestas de la CORRIDA y le contesta al modelo que quedó
para aprobación. Quien invocó la corrida (CLARUS, OFFICIUM R3) recibe la lista
en `propuestas` de la respuesta de `/run` y ejecuta lo que una persona apruebe.

La lista la crea `Agent.run` por corrida y viaja en el context de `tool_fn`
bajo `CLAVE_PROPUESTAS`, al lado de `connections`: dos corridas simultáneas del
mismo agente tienen dos listas y ninguna ve la de la otra. Una corrida
re-entrante (`desde_humano=False`: un sub-agente `type: agent`,
`core/tools.py:263`; un paso de workflow —toda `spec.chain` pasa por ahí—,
`workflow/executor.py:128`; el servidor MCP de astromesh, `mcp/server.py:70`)
no recibe lista: su respuesta no sale en la de `/run`, así que proponer ahí se
rechaza al modelo en vez de perderse callado.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Literal

from astromesh.chain.validate import validate
from astromesh.tools.base import ToolResult

#: Clave del context de `tool_fn` donde viaja la lista de la corrida.
CLAVE_PROPUESTAS = "propuestas"
MAX_PROPUESTAS = 20
MAX_BYTES_ARGUMENTOS = 16 * 1024
AVISO = (
    "Quedó registrado para aprobación; NO se ejecutó. No asumas que se hizo ni "
    "hagas pasos que dependan de su resultado; decí qué propusiste."
)
#: Lo que viaja bajo `CLAVE_PROPUESTAS` cuando la corrida NO puede devolver
#: propuestas: en vez de la lista, el motivo que el handler le contesta al modelo.
SOLO_PRINCIPAL = "esta herramienta sólo propone desde la corrida principal: no se registró nada"
SIN_CANAL = "este canal no admite escrituras con aprobación: no se registró nada"


def handler_de_propuesta(
    tool: str,
    tipo: Literal["api", "mcp"],
    destino: str,
    operacion: str,
    schema: dict,
) -> Callable:
    """El handler de una tool `mode: propose`. `destino` es el slug de la API
    o del servidor tal cual (con guiones) y `operacion` el nombre de la
    operación o de la tool del servidor tal cual: es lo que CLARUS ejecuta."""

    async def _handler(_run_context=None, **argumentos):
        lista = (_run_context or {}).get(CLAVE_PROPUESTAS)
        if not isinstance(lista, list):
            motivo = lista if isinstance(lista, str) else SOLO_PRINCIPAL
            return ToolResult(success=False, data=None, error=motivo).to_dict()
        # `chain/validate.py` y no `jsonschema`: ése es dependencia de dev
        # (`pyproject.toml:61`). Valida `type` (también en lista), `properties`,
        # `required`, `enum` e `items`; lo demás no lo mira.
        try:
            errores = validate(argumentos, schema)
            crudo = json.dumps(argumentos, ensure_ascii=False, separators=(",", ":"))
        except Exception as exc:  # noqa: BLE001
            # Un error acá vuelve al modelo y no sube: si subiera, `Agent.run`
            # fallaría y se perderían las propuestas ya anotadas de la corrida.
            return ToolResult(
                success=False,
                data=None,
                error=f"no se pudieron validar los argumentos, no se registró: {exc}",
            ).to_dict()
        if errores:
            return ToolResult(
                success=False,
                data=None,
                error="argumentos inválidos, no se registró: " + "; ".join(errores[:5]),
            ).to_dict()
        if len(crudo.encode()) > MAX_BYTES_ARGUMENTOS:
            return ToolResult(
                success=False,
                data=None,
                error=(
                    f"los argumentos pasan los {MAX_BYTES_ARGUMENTOS // 1024} KB: no se registró"
                ),
            ).to_dict()
        # Sin `await` entre el chequeo y el `append`: dos llamadas en paralelo
        # de la misma corrida no pueden pasar el tope entre las dos.
        if len(lista) >= MAX_PROPUESTAS:
            return ToolResult(
                success=False,
                data=None,
                error=(
                    f"ya hay {MAX_PROPUESTAS} escrituras propuestas en esta corrida: "
                    "no se registró. Decí en tu respuesta qué quedó sin proponer."
                ),
            ).to_dict()
        lista.append(
            {
                "tool": tool,
                "tipo": tipo,
                "destino": destino,
                "operacion": operacion,
                # Una copia: lo que el patrón haga después con `argumentos` no
                # cambia lo que se aprueba.
                "argumentos": json.loads(crudo),
            }
        )
        return ToolResult(success=True, data=AVISO).to_dict()

    _handler.wants_run_context = True
    return _handler
