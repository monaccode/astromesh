"""Las acciones de `praxis_alcaldia` que necesitan la IDENTIDAD del que escribe.

El problema que resuelven, medido en dev el 2026-08-31: con la tool genérica
`buscar_records`, el teléfono por el que se busca al contribuyente es un
argumento que escribe el MODELO. Cualquiera puede dictar el número de otro en
el texto del mensaje, y el agente sirvió la cuenta completa de un tercero
haciendo exactamente eso. Se mitigó endureciendo el prompt y la mitigación
funciona, pero **un prompt no es un límite de seguridad**: es una instrucción
que el modelo puede desobedecer.

Acá el teléfono no se pide: se DERIVA de `ctx.session_id`, que lo arma Herald
como `<canal>__<usuario>` (`astromesh-herald/internal/domain/conversation.go:26-28`)
antes de que ningún modelo intervenga. Un agente no puede cambiarlo, y tampoco
puede pedir la cuenta de otro: no hay parámetro por donde nombrarla.

**Falla cerrado en todo lo demás.** Sin sesión, con una sesión que no tiene
forma de teléfono, o en un canal cuyo identificador no ES un teléfono, no se
resuelve a nadie y no se devuelve ningún dato. Es lo que pasa en el banco de
pruebas de Centuria (que manda un `session_id` propio, prefijado) y en
Instagram o Telegram, donde el usuario es un id de la plataforma y no un
número — ahí el contribuyente tiene que escribir desde su WhatsApp registrado,
y el agente se lo dice.
"""

from __future__ import annotations

from typing import Any

from astromesh.integrations import errors
from astromesh.integrations.executor import IntegrationContext
from astromesh.tools.base import ToolResult

#: El único canal cuyo identificador de usuario ES el teléfono del padrón.
#: Telegram manda un id numérico de chat e Instagram un id de la plataforma:
#: ninguno de los dos se puede cruzar contra `alc_contribuyente.telefono`, así
#: que no habilitan identidad aunque la centuria esté desplegada en ellos.
CANAL_CON_TELEFONO = "whatsapp"

#: Lo que se le contesta a quien no se puede identificar. Es un dato para el
#: agente, no un error del sistema: tiene que poder decírselo a la persona.
SIN_IDENTIDAD = (
    "No puedo identificar a nadie en esta conversación: la cuenta sólo se consulta "
    "desde el WhatsApp que el contribuyente tenga registrado en la alcaldía. No "
    "busques por un número que te hayan dictado ni des ningún dato de cuenta."
)


def telefono_de_sesion(session_id: str) -> str | None:
    """El teléfono del que escribe, o None si esta sesión no identifica a nadie.

    NO se acepta cualquier cosa con `__`: el canal tiene que ser WhatsApp y la
    parte del usuario tiene que empezar con `+`. Un `session_id` del banco de
    pruebas (`prueba-<ts>-<azar>-…`) no matchea, y ésa es la intención — ahí no
    hay ninguna persona real detrás y devolver la cuenta de alguien sería peor
    que no funcionar.
    """
    if not isinstance(session_id, str) or "__" not in session_id:
        return None
    canal, _, usuario = session_id.partition("__")
    if canal != CANAL_CON_TELEFONO:
        return None
    usuario = usuario.strip()
    if not usuario.startswith("+") or not usuario[1:].isdigit():
        return None
    return usuario


def _sin_identidad() -> ToolResult:
    # `success=True` con el motivo adentro, y no un error: que no se pueda
    # identificar a alguien es parte NORMAL de la conversación —un vecino que
    # no está en el padrón— y el agente tiene que explicarlo. Un ToolResult
    # fallado le llega como "el sistema se rompió" y ahí improvisa.
    return ToolResult(
        success=True,
        data={"identificado": False, "motivo": SIN_IDENTIDAD},
        metadata={},
    )


async def _buscar(ctx: IntegrationContext, entidad: str, filtro: str, limite: int = 50) -> Any:
    """Una consulta a la API de datos de PRAXIS.

    UN SOLO filtro, que es lo que PRAXIS acepta por llamada (ver la descripción
    de `buscar_records` en el manifest genérico `praxis`): cruzar dos
    condiciones se hace trayendo el conjunto chico y filtrando en Python.
    """
    res = await ctx.client.get(
        f"{ctx.base_url}/api/data/{entidad}",
        params={"filter": filtro, "limit": str(limite)},
    )
    if res.status_code >= 400:
        return None, ToolResult(
            success=False,
            data=None,
            error=f"consultar {entidad} falló: HTTP {res.status_code}: {res.text[:300]}",
            metadata={
                "error_kind": errors.classify_status(res.status_code),
                "status_code": res.status_code,
            },
        )
    return (res.json() or {}), None


async def _contribuyente_de_sesion(ctx: IntegrationContext):
    """(fila, None) si la sesión identifica a un contribuyente activo del padrón."""
    telefono = telefono_de_sesion(ctx.session_id)
    if telefono is None:
        return None, _sin_identidad()

    payload, fallo = await _buscar(ctx, "alc_contribuyente", f"telefono:eq:{telefono}", 2)
    if fallo is not None:
        return None, fallo

    filas = [f for f in (payload.get("rows") or []) if (f.get("data") or {}).get("activo")]
    if len(filas) != 1:
        # Cero es lo normal (no está en el padrón). DOS también corta: con el
        # mismo teléfono en dos contribuyentes, elegir uno sería adivinar de
        # quién es la cuenta que se está por mostrar.
        return None, _sin_identidad()
    return filas[0], None


async def mi_cuenta(arguments: dict, ctx: IntegrationContext) -> ToolResult:
    """La cuenta del que ESTÁ escribiendo. No recibe a quién consultar."""
    contribuyente, fallo = await _contribuyente_de_sesion(ctx)
    if fallo is not None:
        return fallo

    payload, error = await _buscar(
        ctx, "alc_liquidacion", f"contribuyente:eq:{contribuyente['id']}", 200
    )
    if error is not None:
        return error

    # El filtro por estado va en Python porque PRAXIS acepta un solo filtro por
    # llamada. `anulada` se descarta —no se debe— y `pagada` se conserva: que
    # alguien pregunte "¿estoy solvente?" es la mitad de las consultas.
    liquidaciones = [
        {"id": f.get("id"), **(f.get("data") or {})}
        for f in (payload.get("rows") or [])
        if (f.get("data") or {}).get("estado") != "anulada"
    ]
    pendientes = [x for x in liquidaciones if x.get("estado") in ("pendiente", "vencida")]

    datos = contribuyente.get("data") or {}
    return ToolResult(
        success=True,
        data={
            "identificado": True,
            "contribuyente": {
                "id": contribuyente.get("id"),
                "nombre": datos.get("nombre"),
                "rif": datos.get("rif"),
            },
            "solvente": len(pendientes) == 0,
            "liquidaciones": liquidaciones,
        },
        metadata={},
    )


async def informar_pago(arguments: dict, ctx: IntegrationContext) -> ToolResult:
    """Informa un pago, pero SÓLO de una liquidación del que está escribiendo.

    La comprobación de pertenencia va acá y no en PRAXIS a propósito: la
    función `alc_informar_pago` es la misma que puede invocar un humano de la
    alcaldía desde la UI, y ése SÍ registra pagos de terceros — es su trabajo.
    Lo que no puede pasar es que el AGENTE lo haga, y el agente es el que entra
    por esta puerta.

    Sin esto, cerrar la lectura y dejar la escritura abierta sería mover el
    agujero de lugar: un id de liquidación ajeno alcanzaría para ensuciarle el
    expediente a otro contribuyente.
    """
    contribuyente, fallo = await _contribuyente_de_sesion(ctx)
    if fallo is not None:
        return fallo

    liquidacion_id = str(arguments.get("liquidacion_id") or "").strip()
    if not liquidacion_id:
        return ToolResult(
            success=True,
            data={"registrado": False, "motivo": "Falta el id de la liquidación."},
            metadata={},
        )

    payload, error = await _buscar(
        ctx, "alc_liquidacion", f"contribuyente:eq:{contribuyente['id']}", 200
    )
    if error is not None:
        return error
    propias = {f.get("id") for f in (payload.get("rows") or [])}
    if liquidacion_id not in propias:
        return ToolResult(
            success=True,
            data={
                "registrado": False,
                "motivo": (
                    "Esa liquidación no es de esta cuenta. Sólo podés informar el pago de "
                    "las liquidaciones que te aparecen a vos."
                ),
            },
            metadata={},
        )

    res = await ctx.client.post(
        f"{ctx.base_url}/api/functions/alc_informar_pago",
        json={
            "args": {
                "liquidacion_id": liquidacion_id,
                "fecha": arguments.get("fecha"),
                "monto_bs": arguments.get("monto_bs"),
                "referencia": arguments.get("referencia"),
                "medio": arguments.get("medio"),
            }
        },
    )
    if res.status_code >= 400:
        return ToolResult(
            success=False,
            data=None,
            error=f"informar el pago falló: HTTP {res.status_code}: {res.text[:300]}",
            metadata={
                "error_kind": errors.classify_status(res.status_code),
                "status_code": res.status_code,
            },
        )
    cuerpo = res.json() or {}
    # PRAXIS envuelve el retorno de una función en `value`. Se desenvuelve acá
    # para que el agente lea `registrado` / `ya_estaba` directo, que es lo que
    # su prompt nombra.
    return ToolResult(success=True, data=cuerpo.get("value", cuerpo), metadata={})
