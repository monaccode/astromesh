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
conserva por un Herald anterior al que manda `sender_phone`; acá se EXIGE el
campo que Herald escribe (`astromesh-herald/internal/app/receive.go:146`,
`"sender_phone": telefonoDelRemitente(...)`), porque el respaldo abriría un
camino que un `session_id` inventado podría recorrer. Sin ese campo la acción
contesta `SIN_IDENTIDAD`, que es una negativa visible y nunca el dato de otro.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
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


async def _buscar(
    ctx: IntegrationContext,
    entidad: str,
    filtro: str | list[str],
    limite: int = 50,
    orden: str | None = None,
):
    """Una consulta a la API de datos. `filtro` puede ser UNO o VARIOS.

    PRAXIS acepta `filter` repetido y los combina con AND:
    `praxis/apps/backend/src/records/query-params.util.ts:10` lo documenta
    (`?filter=field:op:value (repeatable; AND-combined)`) y `:100` lo
    implementa (`toStringArray(query.filter).map(parseFilter)`). El que admite
    un solo filtro es el manifest genérico `praxis`, donde es un parámetro
    string del modelo (`catalog/praxis/integration.yaml:33`) — y estos
    handlers no pasan por ahí, llaman a httpx directo.

    `orden` es el `sort` de PRAXIS (`query-params.util.ts:12`,
    `?sort=field:asc`). El campo se resuelve contra los campos DECLARADOS de la
    entidad y uno desconocido es un 422, nunca un orden ignorado
    (`query-builder.ts:224-227`): `created_at` no es un campo declarado, así
    que ordenar por fecha sólo se puede donde la entidad tiene una.

    `params={...}` y NO una query armada a mano: httpx encodea `+` como `%2B`,
    y ES lo que tiene que pasar. El parser de query strings del lado de PRAXIS
    (Express, `qs`) decodifica un `+` LITERAL como espacio — es el default de
    `application/x-www-form-urlencoded` — así que un filtro con un `+` sin
    escapar (`telefono:eq:+549…`) le llega al servidor como `telefono:eq: 549…`
    y no matchea a nadie. `%2B` es lo único que decodifica de vuelta a `+` del
    otro lado. `praxis_alcaldia` usa esta misma forma y anda medido en dev con
    teléfonos `+58…`.
    """
    params: dict[str, Any] = {"filter": filtro, "limit": str(limite)}
    if orden:
        params["sort"] = orden
    res = await ctx.client.get(f"{ctx.base_url}/api/data/{entidad}", params=params)
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

    # Cinco y no dos: las de baja se descartan ACÁ, en Python, así que un
    # `limit` justo al tope del guard lo esquiva — con tres fichas del mismo
    # número (una de baja y dos activas) `limit=2` podía traer [baja, activa],
    # dejar UNA fila y servirle la ficha a una de las dos que se disputan el
    # teléfono. El margen tiene que ser mayor que el número de fichas de baja
    # plausibles sobre un mismo número.
    payload, fallo = await _buscar(ctx, "lca_productor", f"telefono:eq:{telefono}", 5)
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
    return False


async def _oferta_habilitada(ctx: IntegrationContext, productor_id: str, membresia: str) -> bool:
    """Reglas de spec §15.2, contadas sobre lo que quedó REGISTRADO.

    A lo sumo 2 respuestas registradas (`interes_membresia` / `oferta_rechazada`)
    por trimestre, y ninguna oferta en los 30 días posteriores a un "no". No
    cuenta ofertas: una oferta que la persona ignoró no deja fila y no consume
    cuota — el registro es lo único que existe de este lado."""
    if membresia == "paga":
        return False
    # No sólo el status HTTP: un error de transporte (timeout, red caída) no
    # puede tirar abajo `mi_ficha` entera por un campo secundario. Cierra en
    # `False` — el peor caso es no ofrecer la membresía, nunca romper la ficha.
    try:
        # Los DOS tipos que cuentan van en la query y no en el `if` de abajo:
        # `lca_pendiente` acumula también los escalamientos, y traer los 50
        # primeros pendientes del productor para descartar casi todos dejaba
        # afuera las respuestas viejas apenas alguien escalaba seguido.
        # Ordenar por fecha no es una opción acá: `lca_pendiente` no declara
        # ningún campo de fecha de alta (`praxis/apps/backend/src/packages/lca/
        # lca.package.ts:366-390`) y `created_at` no es un campo declarado.
        payload, fallo = await _buscar(
            ctx,
            "lca_pendiente",
            [f"productor:eq:{productor_id}", "tipo:in:interes_membresia,oferta_rechazada"],
            50,
        )
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
        # Dato útil, no precondición: igual que `_oferta_habilitada`, un
        # fallo acá (de red o de status) no puede tumbar la ficha entera.
        # Con log del motivo, nunca un catch mudo.
        try:
            res = await ctx.client.patch(
                f"{ctx.base_url}/api/data/lca_productor/{productor_id}",
                json={"direccion_canal": direccion.strip()},
            )
            if res.status_code >= 400:
                logger.warning(
                    "no se pudo guardar direccion_canal para %s: HTTP %s",
                    productor_id,
                    res.status_code,
                )
        except Exception:
            logger.warning(
                "no se pudo guardar direccion_canal para %s: PATCH falló",
                productor_id,
                exc_info=True,
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
    # El MISMO helper que las otras cuatro acciones que reciben un id: dos
    # caminos para la misma comprobación divergen el día que uno se arregla.
    fallo = await _suyo_o_fallo(ctx, "lca_producto", producto_id, str(productor["id"]))
    if fallo is not None:
        return fallo

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


async def _invocar(ctx: IntegrationContext, funcion: str, args: dict[str, Any]):
    """Una función de PRAXIS.

    La ruta es `POST /api/functions/<api_name>` —**sin** `/invoke`— con body
    `{"args": {...}}`, y la respuesta es `{"value": ...}`. Verificado en
    `praxis/apps/backend/src/functions/functions.controller.ts:84-105`.
    """
    res = await ctx.client.post(f"{ctx.base_url}/api/functions/{funcion}", json={"args": args})
    if res.status_code >= 400:
        return None, _fallo(
            f"{funcion} falló: HTTP {res.status_code}: {res.text[:300]}", res.status_code
        )
    cuerpo = res.json() or {}
    return cuerpo.get("value"), None


async def mi_stock(arguments: dict[str, Any], ctx: IntegrationContext) -> ToolResult:
    productor, fallo = await _productor_de_sesion(ctx)
    if fallo is not None:
        return fallo
    # El `productor` de la función sale de la SESIÓN. Si el modelo mandó un
    # `productor_id` en `arguments`, acá no se lee: no existe ese parámetro.
    datos, fallo = await _invocar(
        ctx, "lca_stock_y_proyeccion", {"productor": str(productor["id"])}
    )
    if fallo is not None:
        return fallo
    return ToolResult(success=True, data=datos, metadata={})


async def mi_resumen(arguments: dict[str, Any], ctx: IntegrationContext) -> ToolResult:
    from zoneinfo import ZoneInfo

    productor, fallo = await _productor_de_sesion(ctx)
    if fallo is not None:
        return fallo
    try:
        semanas = max(1, min(8, int(arguments.get("semanas") or 1)))
    except (TypeError, ValueError):
        semanas = 1

    # El negocio está en Belgrano (Argentina, UTC-3), no en UTC: entre las
    # 21:00 y la medianoche locales el día en UTC ya saltó al siguiente, y con
    # `datetime.now(UTC).date()` un domingo a la noche calculaba "hoy" como
    # lunes, corriendo toda la ventana de semanas antes de tiempo.
    hoy = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    lunes = hoy - timedelta(days=(hoy.weekday()))
    salida = []
    for i in range(semanas):
        desde = lunes - timedelta(days=7 * (i + 1))
        datos, fallo = await _invocar(
            ctx,
            "lca_reporte_semanal",
            {"productor": str(productor["id"]), "desde": desde.isoformat()},
        )
        if fallo is not None:
            return fallo
        salida.append(datos)
    return ToolResult(success=True, data={"semanas": salida}, metadata={})


async def mis_envios_abiertos(arguments: dict[str, Any], ctx: IntegrationContext) -> ToolResult:
    productor, fallo = await _productor_de_sesion(ctx)
    if fallo is not None:
        return fallo

    payload, fallo = await _buscar(ctx, "lca_producto", f"productor:eq:{productor['id']}", 200)
    if fallo is not None:
        return fallo
    mios = {str(f["id"]): (f.get("data") or {}) for f in (payload.get("rows") or [])}
    # Sin productos no puede haber un envío suyo. Cortar acá es además lo que
    # impide armar un `producto:in:` VACÍO abajo, que no filtraría por producto
    # y traería los envíos abiertos de todo el tenant.
    if not mios:
        return ToolResult(success=True, data={"envios": []}, metadata={})

    # DOS filtros, AND del lado de PRAXIS: el aislamiento viaja en la QUERY.
    # Antes se traían los abiertos de todo el tenant y se recortaban en Python:
    # con 300 productores eso pasa las 200 filas sin esfuerzo (el techo de
    # PRAXIS es 500, `records/query-builder.ts:94`), y un envío propio que
    # quedaba fuera de la página se veía como "no tenés nada pendiente".
    envios, fallo = await _buscar(
        ctx,
        "lca_envio",
        ["estado:in:propuesto,confirmado", f"producto:in:{','.join(mios)}"],
        200,
    )
    if fallo is not None:
        return fallo

    salida = []
    for fila in envios.get("rows") or []:
        d = fila.get("data") or {}
        # Segundo cierre: la query ya filtró por los productos propios, pero el
        # nombre y la presentación salen de este mapa igual.
        producto = mios.get(str(d.get("producto") or ""))
        if producto is None:
            continue
        salida.append(
            {
                "envio_id": fila.get("id"),
                "producto": producto.get("nombre"),
                "presentacion": producto.get("presentacion"),
                "estado": d.get("estado"),
                "cantidad_sugerida": d.get("cantidad_sugerida"),
                "cantidad": d.get("cantidad"),
                "vence_el": d.get("vence_el"),
            }
        )
    return ToolResult(success=True, data={"envios": salida}, metadata={})


async def mis_liquidaciones(arguments: dict[str, Any], ctx: IntegrationContext) -> ToolResult:
    productor, fallo = await _productor_de_sesion(ctx)
    if fallo is not None:
        return fallo
    # Las MÁS RECIENTES primero: sin `sort`, pasadas las 50 filas las que
    # vuelven son arbitrarias (`records/query-builder.ts:341-344` — sin orden,
    # "whatever order Postgres feels like") y a un productor viejo se le podía
    # contestar con las liquidaciones de 2024. `periodo` es `AAAA-MM`, así que
    # el orden lexicográfico ES el cronológico, y está declarado e indexado
    # (`praxis/apps/backend/src/packages/lca/lca.package.ts:313`).
    payload, fallo = await _buscar(
        ctx,
        "lca_liquidacion",
        f"productor:eq:{productor['id']}",
        50,
        orden="periodo:desc",
    )
    if fallo is not None:
        return fallo

    salida = []
    for fila in payload.get("rows") or []:
        d = fila.get("data") or {}
        # Un BORRADOR no llega nunca al productor: es un número que La Carta
        # todavía no aprobó, y prometerlo sería prometer una plata que puede
        # cambiar.
        if d.get("estado") not in {"aprobada", "acreditada"}:
            continue
        salida.append(
            {
                "periodo": d.get("periodo"),
                "unidades": d.get("unidades"),
                "neto": d.get("neto"),
                "estado": d.get("estado"),
                "fecha_acreditacion": d.get("fecha_acreditacion"),
            }
        )
    return ToolResult(success=True, data={"liquidaciones": salida}, metadata={})


async def _suyo_o_fallo(ctx: IntegrationContext, entidad: str, id_: str, productor_id: str):
    """La pertenencia SIEMPRE se verifica antes de invocar la función de PRAXIS
    que escribe: un envío o un pedido de reposición mueve stock, y confirmar o
    pedir sobre lo de otro productor sería mover el suyo.

    **Divergencia DELIBERADA con el molde**: `praxis_alcaldia:266-276` devuelve
    `success=True` con un `motivo` cuando algo no es de la cuenta, argumentando
    (`praxis_alcaldia:86-88`) que un ToolResult fallado le llega al modelo como
    "el sistema se rompió". Acá se eligió `success=False` con un `error` claro,
    que es lo que hacen las trece acciones de esta integración: un id ajeno lo
    pone el MODELO (la persona nunca los ve), así que no es un caso normal de
    conversación como un vecino fuera del padrón, y uniformar la forma de fallar
    vale más que la diferencia de tono. No es un descuido."""
    if not id_:
        return _fallo("falta el id", 400)
    # Mismo mensaje para "no existe" y "es de otro": distinguirlos le diría a
    # quien prueba ids cuáles existen.
    if not await _es_suyo(ctx, entidad, id_, productor_id):
        return _fallo("eso no es tuyo o no existe", 404)
    return None


async def confirmar_envio(arguments: dict[str, Any], ctx: IntegrationContext) -> ToolResult:
    productor, fallo = await _productor_de_sesion(ctx)
    if fallo is not None:
        return fallo
    envio_id = str(arguments.get("envio_id") or "").strip()
    fallo = await _suyo_o_fallo(ctx, "lca_envio", envio_id, str(productor["id"]))
    if fallo is not None:
        return fallo
    if arguments.get("cantidad") is None:
        return _fallo("falta la cantidad", 400)
    datos, fallo = await _invocar(
        ctx, "lca_confirmar_envio", {"envio": envio_id, "cantidad": arguments.get("cantidad")}
    )
    if fallo is not None:
        return fallo
    return ToolResult(success=True, data=datos, metadata={})


async def rechazar_envio(arguments: dict[str, Any], ctx: IntegrationContext) -> ToolResult:
    productor, fallo = await _productor_de_sesion(ctx)
    if fallo is not None:
        return fallo
    envio_id = str(arguments.get("envio_id") or "").strip()
    fallo = await _suyo_o_fallo(ctx, "lca_envio", envio_id, str(productor["id"]))
    if fallo is not None:
        return fallo
    datos, fallo = await _invocar(ctx, "lca_rechazar_envio", {"envio": envio_id})
    if fallo is not None:
        return fallo
    return ToolResult(success=True, data=datos, metadata={})


async def pedir_reposicion(arguments: dict[str, Any], ctx: IntegrationContext) -> ToolResult:
    productor, fallo = await _productor_de_sesion(ctx)
    if fallo is not None:
        return fallo
    producto_id = str(arguments.get("producto_id") or "").strip()
    fallo = await _suyo_o_fallo(ctx, "lca_producto", producto_id, str(productor["id"]))
    if fallo is not None:
        return fallo
    if arguments.get("cantidad") is None:
        return _fallo("falta la cantidad", 400)
    datos, fallo = await _invocar(
        ctx,
        "lca_pedir_reposicion",
        {"producto": producto_id, "cantidad": arguments.get("cantidad")},
    )
    if fallo is not None:
        return fallo
    return ToolResult(success=True, data=datos, metadata={})


#: Los únicos motivos que el YAML le ofrece al modelo. Uno inventado es un
#: prompt confundido, no un caso de negocio nuevo.
MOTIVOS = {"fuera_de_alcance", "error_de_calculo", "baja", "liquidacion", "telefono_desconocido"}


async def escalar(arguments: dict[str, Any], ctx: IntegrationContext) -> ToolResult:
    """La ÚNICA acción que corre sin identidad.

    Es el caso que hay que poder registrar: alguien que dice ser productor de La
    Carta y no está en el padrón. El teléfono sale del CANAL, nunca de un
    argumento — si viniera del modelo, cualquiera podría llenar la bandeja de La
    Carta con números ajenos.
    """
    motivo = str(arguments.get("motivo") or "").strip()
    if motivo not in MOTIVOS:
        return _fallo(f"motivo desconocido: {motivo}", 400)

    productor, fallo = await _productor_de_sesion(ctx)
    # Es la única acción que necesita distinguir "no está en el padrón" de "el
    # padrón no contestó", y la distinción viene gratis: `_sin_identidad()`
    # viaja con `success=True`, un HTTP 500 con `success=False`. Tragarse el
    # segundo abría un pendiente de "teléfono desconocido" para alguien que SÍ
    # está en el padrón —basura en la bandeja de La Carta— o le decía "no puedo
    # identificarte" a un productor legítimo.
    if fallo is not None and fallo.success is False:
        return fallo
    telefono = telefono_del_canal(ctx) or ""

    if productor is None:
        if motivo != "telefono_desconocido":
            return _sin_identidad()
        if not telefono:
            # Sin productor y sin teléfono el pendiente no tiene por dónde
            # volver: nadie de La Carta puede atender un "alguien dice ser
            # productor" sin número ni ficha. Pasa en el banco de pruebas y en
            # una invocación por API, y sin este corte cada llamada agrega una
            # fila indistinguible de la anterior — el dedupe de abajo necesita
            # justamente el teléfono para poder deduplicar.
            return _sin_identidad()
        # Uno solo por teléfono: si ya hay uno abierto, no se abre otro. Sin
        # esto, cinco mensajes de la misma persona son cinco ítems en la bandeja.
        # Los tres filtros van en la QUERY: filtrarlos en Python sobre las 20
        # primeras filas del teléfono se saltea el duplicado en cuanto hay
        # veinte pendientes viejos, y `lca_pendiente` no tiene campo de fecha
        # por el que ordenar para quedarse con los últimos.
        payload, fallo = await _buscar(
            ctx,
            "lca_pendiente",
            [
                f"telefono:eq:{telefono}",
                "tipo:eq:telefono_desconocido",
                "estado:eq:abierto",
            ],
            20,
        )
        if fallo is None and (payload.get("rows") or []):
            return ToolResult(success=True, data={"ya_estaba": True}, metadata={})

    cuerpo: dict[str, Any] = {
        "tipo": "escalamiento" if productor is not None else "telefono_desconocido",
        "estado": "abierto",
        "telefono": telefono,
        "resumen": f"[{motivo}] {str(arguments.get('resumen') or '').strip()}",
    }
    if productor is not None:
        cuerpo["productor"] = str(productor["id"])

    res = await ctx.client.post(f"{ctx.base_url}/api/data/lca_pendiente", json=cuerpo)
    if res.status_code >= 400:
        return _fallo(f"escalar falló: HTTP {res.status_code}: {res.text[:200]}", res.status_code)
    return ToolResult(success=True, data={"escalado": True, "ya_estaba": False}, metadata={})


async def responder_oferta_membresia(
    arguments: dict[str, Any], ctx: IntegrationContext
) -> ToolResult:
    productor, fallo = await _productor_de_sesion(ctx)
    if fallo is not None:
        return fallo
    acepta = bool(arguments.get("acepta"))

    # Mismo dedupe que `escalar`, por el mismo motivo: dos "sí" seguidos en la
    # misma conversación son DOS ítems para que La Carta llame a la misma
    # persona por lo mismo. Sólo sobre el "sí": un "no" nace `resuelto` y no
    # entra a ninguna bandeja, y además la regla de §15.2 cuenta esas filas —
    # deduplicarlas le regalaría cuota a quien dice que no dos veces.
    if acepta:
        payload, fallo = await _buscar(
            ctx,
            "lca_pendiente",
            [
                f"productor:eq:{productor['id']}",
                "tipo:eq:interes_membresia",
                "estado:eq:abierto",
            ],
            20,
        )
        if fallo is None and (payload.get("rows") or []):
            return ToolResult(
                success=True,
                data={"registrado": True, "acepta": True, "ya_estaba": True},
                metadata={},
            )

    # Un "no" se guarda YA RESUELTO: existe para que la regla de oferta lo
    # cuente, no para que nadie lo atienda.
    cuerpo = {
        "tipo": "interes_membresia" if acepta else "oferta_rechazada",
        "estado": "abierto" if acepta else "resuelto",
        "productor": str(productor["id"]),
        "resumen": "Quiere que La Carta lo contacte por la membresía completa."
        if acepta
        else "No quiere la membresía completa por ahora.",
    }
    res = await ctx.client.post(f"{ctx.base_url}/api/data/lca_pendiente", json=cuerpo)
    if res.status_code >= 400:
        return _fallo(
            f"registrar la respuesta falló: HTTP {res.status_code}: {res.text[:200]}",
            res.status_code,
        )
    return ToolResult(
        success=True,
        data={"registrado": True, "acepta": acepta, "ya_estaba": False},
        metadata={},
    )
