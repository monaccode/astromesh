"""Las acciones de `praxis_lca`, todas atadas a la identidad del que escribe.

El problema que resuelven: La Carta Argentina es UN tenant de PRAXIS con ~300
productores adentro, cada uno dueño de sus productos y de sus ventas. El RLS de
PRAXIS es por TENANT (`db/migrations/006_rls_null_guc.ts`), así que la API key
del bot alcanza a los trescientos por igual; y `owner_id` existe pero no filtra
ninguna lectura. O sea: **debajo de estos handlers no hay ninguna barrera**.

Por eso acá:

  1. El teléfono no se pide, se lee de `caller_context["sender_phone"]`, que
     escribe Herald desde el mensaje real (`internal/app/receive.go`) antes de
     que ningún modelo intervenga.
  2. Ninguna acción tiene un parámetro por donde nombrar a un productor.
  3. Toda acción que recibe el id de un producto o de un envío comprueba que
     cuelgue del que escribe, ANTES de llamar a la función que escribe.

**Sin respaldo por `session_id`, a diferencia de `praxis_alcaldia`.** Aquél lo
conserva por un Herald anterior al que manda `sender_phone`; acá los dos
entornos ya lo mandan, y el respaldo abriría un camino que un `session_id`
inventado podría recorrer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from astromesh.integrations import errors
from astromesh.integrations.executor import IntegrationContext
from astromesh.tools.base import ToolResult

logger = logging.getLogger(__name__)

#: Lo que se le contesta a quien no se puede identificar. Es un dato para el
#: agente, no un error: tiene que poder explicárselo a la persona.
SIN_IDENTIDAD = (
    "No puedo identificar a ningún productor en esta conversación. La ficha sólo se "
    "consulta desde el teléfono que La Carta tenga registrado: por WhatsApp es el "
    "número desde el que escribe, y por Telegram hay que tocar el botón para "
    "compartir el número. No busques por un número que te hayan dictado ni des "
    "ningún dato."
)


def telefono_del_canal(ctx: IntegrationContext) -> str | None:
    """El teléfono VERIFICADO de quien escribe, o None.

    Una sola fuente: `caller_context["sender_phone"]`, que en WhatsApp es el
    `from` del mensaje y en Telegram el número que la persona compartió con el
    botón. Nunca los argumentos: ahí escribe el modelo.
    """
    valor = (ctx.caller_context or {}).get("sender_phone")
    if isinstance(valor, str) and valor.strip():
        return valor.strip()
    return None


def _sin_identidad() -> ToolResult:
    return ToolResult(
        success=True, data={"identificado": False, "motivo": SIN_IDENTIDAD}, metadata={}
    )


def _fallo(mensaje: str, status: int) -> ToolResult:
    return ToolResult(
        success=False,
        data=None,
        error=mensaje,
        metadata={"error_kind": errors.classify_status(status), "status_code": status},
    )


async def _buscar(ctx: IntegrationContext, entidad: str, filtro: str, limite: int = 50):
    """Una consulta a la API de datos. UN solo filtro, que es lo que PRAXIS acepta.

    `params={...}` y NO una query armada a mano: httpx encodea `+` como `%2B`,
    y ES lo que tiene que pasar. El parser de query strings del lado de PRAXIS
    (Express, `qs`) decodifica un `+` LITERAL como espacio — es el default de
    `application/x-www-form-urlencoded` — así que un filtro con un `+` sin
    escapar (`telefono:eq:+549…`) le llega al servidor como `telefono:eq: 549…`
    y no matchea a nadie. `%2B` es lo único que decodifica de vuelta a `+` del
    otro lado. `praxis_alcaldia` usa esta misma forma y anda medido en dev con
    teléfonos `+58…`.
    """
    res = await ctx.client.get(
        f"{ctx.base_url}/api/data/{entidad}",
        params={"filter": filtro, "limit": str(limite)},
    )
    if res.status_code >= 400:
        return None, _fallo(
            f"consultar {entidad} falló: HTTP {res.status_code}: {res.text[:300]}", res.status_code
        )
    return (res.json() or {}), None


async def _productor_de_sesion(ctx: IntegrationContext):
    """(fila, None) si el canal identifica a UN productor que no está de baja."""
    telefono = telefono_del_canal(ctx)
    if telefono is None:
        return None, _sin_identidad()

    payload, fallo = await _buscar(ctx, "lca_productor", f"telefono:eq:{telefono}", 2)
    if fallo is not None:
        return None, fallo

    filas = [
        f for f in (payload.get("rows") or []) if (f.get("data") or {}).get("estado") != "baja"
    ]
    # Cero es lo normal (no está en el padrón). DOS también corta: con el mismo
    # teléfono en dos fichas, elegir una sería adivinar de quién es el negocio
    # que se está por mostrar.
    if len(filas) != 1:
        return None, _sin_identidad()
    return filas[0], None


async def _es_suyo(ctx: IntegrationContext, entidad: str, id_: str, productor_id: str) -> bool:
    """¿Ese producto (o el producto de ese envío) es del productor que escribe?

    Es el segundo cierre, y el que importa cuando el modelo SÍ tiene un id: el
    primero impide nombrar a otro productor, éste impide tocar algo suyo.
    """
    res = await ctx.client.get(f"{ctx.base_url}/api/data/{entidad}/{id_}")
    if res.status_code >= 400:
        return False
    datos = (res.json() or {}).get("data") or {}
    if entidad == "lca_producto":
        return datos.get("productor") == productor_id
    if entidad == "lca_envio":
        producto_id = datos.get("producto")
        if not producto_id:
            return False
        return await _es_suyo(ctx, "lca_producto", str(producto_id), productor_id)
    if entidad == "lca_liquidacion":
        return datos.get("productor") == productor_id
    return False


async def _oferta_habilitada(ctx: IntegrationContext, productor_id: str, membresia: str) -> bool:
    """Reglas de spec §15.2: a lo sumo 2 ofertas por trimestre, y ninguna en los
    30 días posteriores a un "no". Se cuenta sobre `lca_pendiente`, que es donde
    quedan registradas — el registro ES el dato que dice qué vende la membresía."""
    if membresia == "paga":
        return False
    # No sólo el status HTTP: un error de transporte (timeout, red caída) no
    # puede tirar abajo `mi_ficha` entera por un campo secundario. Cierra en
    # `False` — el peor caso es no ofrecer la membresía, nunca romper la ficha.
    try:
        payload, fallo = await _buscar(ctx, "lca_pendiente", f"productor:eq:{productor_id}", 50)
    except Exception:
        # No es lo mismo «la regla dice que no» que «no pudimos consultar la
        # regla»: sin este log, un timeout de red se ve exactamente igual que
        # un productor que ya usó sus dos ofertas del trimestre.
        logger.warning(
            "no se pudo evaluar puede_ofrecer_membresia para %s: consulta a lca_pendiente falló",
            productor_id,
            exc_info=True,
        )
        return False
    if fallo is not None:
        return False

    from datetime import UTC, datetime, timedelta

    ahora = datetime.now(UTC)
    trimestre = 0
    for fila in payload.get("rows") or []:
        datos = fila.get("data") or {}
        if datos.get("tipo") not in {"interes_membresia", "oferta_rechazada"}:
            continue
        creado = str(fila.get("created_at") or datos.get("created_at") or "")[:10]
        if not creado:
            continue
        try:
            fecha = datetime.fromisoformat(creado).replace(tzinfo=UTC)
        except ValueError:
            continue
        if ahora - fecha <= timedelta(days=90):
            trimestre += 1
        if datos.get("tipo") == "oferta_rechazada" and ahora - fecha <= timedelta(days=30):
            return False
    return trimestre < 2


async def mi_ficha(arguments: dict[str, Any], ctx: IntegrationContext) -> ToolResult:
    """La ficha del que ESTÁ escribiendo. No recibe a quién consultar."""
    productor, fallo = await _productor_de_sesion(ctx)
    if fallo is not None:
        return fallo

    datos = productor.get("data") or {}
    productor_id = str(productor["id"])

    # Aprende la dirección de vuelta del canal. La escribe el HANDLER desde el
    # contexto —nunca el modelo— y sólo cuando cambió: en Telegram la dirección
    # es un chat_id que no se parece al teléfono, y sin ella el cron no tiene a
    # dónde mandarle el reporte del lunes.
    direccion = (ctx.caller_context or {}).get("sender")
    if (
        isinstance(direccion, str)
        and direccion.strip()
        and datos.get("direccion_canal") != direccion.strip()
    ):
        await ctx.client.patch(
            f"{ctx.base_url}/api/data/lca_productor/{productor_id}",
            json={"direccion_canal": direccion.strip()},
        )

    payload, fallo = await _buscar(ctx, "lca_producto", f"productor:eq:{productor_id}", 200)
    if fallo is not None:
        return fallo

    productos = []
    for fila in payload.get("rows") or []:
        d = fila.get("data") or {}
        if d.get("activo") is False:
            continue
        productos.append(
            {
                "id": fila.get("id"),
                "nombre": d.get("nombre"),
                "presentacion": d.get("presentacion"),
                "precio_publico": d.get("precio_publico"),
                "lote_minimo": d.get("lote_minimo"),
            }
        )

    return ToolResult(
        success=True,
        data={
            "identificado": True,
            "productor_id": productor_id,
            "nombre_comercial": datos.get("nombre_comercial"),
            "estado": datos.get("estado"),
            "membresia": datos.get("membresia"),
            "email": datos.get("email"),
            "alta_completada": bool(datos.get("alta_completada_el")),
            "productos": productos,
            "puede_ofrecer_membresia": await _oferta_habilitada(
                ctx, productor_id, str(datos.get("membresia") or "gratuita")
            ),
        },
        metadata={},
    )


async def corregir_producto(arguments: dict[str, Any], ctx: IntegrationContext) -> ToolResult:
    productor, fallo = await _productor_de_sesion(ctx)
    if fallo is not None:
        return fallo
    producto_id = str(arguments.get("producto_id") or "").strip()
    if not producto_id:
        return _fallo("falta el id del producto", 400)
    if not await _es_suyo(ctx, "lca_producto", producto_id, str(productor["id"])):
        # Mismo mensaje para "no existe" y "es de otro": distinguirlos le diría
        # a quien prueba ids cuáles existen.
        return _fallo("ese producto no es tuyo o no existe", 404)

    patch = {
        campo: arguments[campo]
        for campo in ("nombre", "presentacion", "precio_publico")
        if arguments.get(campo) is not None
    }
    if not patch:
        return _fallo("no me dijiste qué cambiar", 400)

    res = await ctx.client.patch(f"{ctx.base_url}/api/data/lca_producto/{producto_id}", json=patch)
    if res.status_code >= 400:
        return _fallo(
            f"corregir el producto falló: HTTP {res.status_code}: {res.text[:200]}", res.status_code
        )
    return ToolResult(
        success=True, data={"producto_id": producto_id, "cambiado": list(patch)}, metadata={}
    )


async def agregar_producto(arguments: dict[str, Any], ctx: IntegrationContext) -> ToolResult:
    productor, fallo = await _productor_de_sesion(ctx)
    if fallo is not None:
        return fallo
    nombre = str(arguments.get("nombre") or "").strip()
    if not nombre:
        return _fallo("falta el nombre del producto", 400)

    # El código de Belgrano lo sabe SÓLO La Carta. Un provisorio hace que las
    # ventas de este producto se rechacen con ese motivo hasta que lo carguen,
    # que es mejor que aparear contra el producto equivocado.
    sku = f"pendiente:{uuid.uuid4()}"
    res = await ctx.client.post(
        f"{ctx.base_url}/api/data/lca_producto",
        json={
            "nombre": nombre,
            "presentacion": arguments.get("presentacion"),
            "precio_publico": arguments.get("precio_publico"),
            "sku_externo": sku,
            "productor": str(productor["id"]),
        },
    )
    if res.status_code >= 400:
        return _fallo(
            f"crear el producto falló: HTTP {res.status_code}: {res.text[:200]}", res.status_code
        )
    return ToolResult(
        success=True,
        data={"producto_id": (res.json() or {}).get("id"), "sku_externo": sku, "provisorio": True},
        metadata={},
    )


async def completar_alta(arguments: dict[str, Any], ctx: IntegrationContext) -> ToolResult:
    productor, fallo = await _productor_de_sesion(ctx)
    if fallo is not None:
        return fallo
    email = str(arguments.get("email") or "").strip()
    if not email:
        return _fallo("falta el mail", 400)

    res = await ctx.client.patch(
        f"{ctx.base_url}/api/data/lca_productor/{productor['id']}",
        json={
            "email": email,
            "estado": "activo",
            "alta_completada_el": datetime.now(UTC).isoformat(),
        },
    )
    if res.status_code >= 400:
        return _fallo(
            f"completar el alta falló: HTTP {res.status_code}: {res.text[:200]}", res.status_code
        )
    return ToolResult(
        success=True, data={"productor_id": str(productor["id"]), "estado": "activo"}, metadata={}
    )
