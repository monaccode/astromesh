"""`praxis_lca`: la integración que hace que un productor no pueda ver lo de otro.

La Carta es UN tenant con ~300 productores, y PRAXIS separa por tenant y no por
fila: la API key del bot alcanza a los 300. El aislamiento entre productores
vive acá, en estos handlers, y por eso los tests que más valen no son los de
forma sino los que prueban que **no hay forma de pedir lo de otro** — ni por
parámetro, ni dictando un teléfono, ni con un id ajeno.
"""

import json
from datetime import UTC, datetime, timedelta

import httpx
import respx

from astromesh.integrations import IntegrationCatalog
from astromesh.integrations.catalog.praxis_lca import handlers
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor

BASE = "https://praxis.lacarta.test"
TELEFONO = "+5491155512345"
PRODUCTOR = "p-1"
CTX = {"channel": "whatsapp", "sender": TELEFONO, "sender_phone": TELEFONO}


def _lca():
    catalog = IntegrationCatalog()
    catalog.discover()
    return catalog.get("praxis_lca")


def _conn():
    return ResolvedConnection(name="praxis", material={"api_key": "praxis_K"}, base_url=BASE)


async def _correr(accion: str, args: dict | None = None, ctx: dict | None = CTX):
    m = _lca()
    return await HttpActionExecutor().execute(
        m,
        m.action(accion),
        args or {},
        _conn(),
        agent_name="empleado",
        session_id="t_x__empleado__whatsapp__" + TELEFONO,
        caller_context=ctx,
    )


def _padron(estado="activo", membresia="gratuita", direccion=TELEFONO):
    return httpx.Response(
        200,
        json={
            "rows": [
                {
                    "id": PRODUCTOR,
                    "data": {
                        "nombre_comercial": "Miel del Talar",
                        "telefono": TELEFONO,
                        "estado": estado,
                        "membresia": membresia,
                        "direccion_canal": direccion,
                        "email": None,
                        "alta_completada_el": None,
                    },
                }
            ],
            "total": 1,
        },
    )


def _vacio():
    return httpx.Response(200, json={"rows": [], "total": 0})


def _instante_fijo(monkeypatch, iso_utc: str):
    """Congela `datetime.now(tz)` dentro de `handlers` a un instante fijo (dado
    en UTC), para poder poner al servidor "del otro lado" de la medianoche
    argentina sin depender de la hora real de quien corre el test."""
    fijo = datetime.fromisoformat(iso_utc)

    class _DatetimeFijo(datetime):
        @classmethod
        def now(cls, tz=None):
            return fijo.astimezone(tz) if tz is not None else fijo

    monkeypatch.setattr(handlers, "datetime", _DatetimeFijo)


# --- Forma -----------------------------------------------------------------


def test_ninguna_accion_recibe_la_identidad_como_parametro():
    """El invariante de la vertical: si un parámetro pudiera nombrar a un
    productor, el modelo podría nombrar a otro."""
    m = _lca()
    prohibidos = {"productor", "productor_id", "telefono", "sender", "sender_phone"}
    for accion in m.actions:
        assert not (set(accion.parameters) & prohibidos), f"{accion.name} nombra la identidad"


def test_los_parametros_de_cada_accion_son_exactamente_estos():
    """La lista negra de arriba la esquiva un parámetro con otro nombre
    (`numero`, `wa_id`). Esto fija la lista COMPLETA por acción: agregar
    cualquier parámetro nuevo, se llame como se llame, tiene que tocar este
    test — y un revisor lo ve en el diff."""
    m = _lca()
    esperados = {
        "mi_ficha": set(),
        "corregir_producto": {"producto_id", "nombre", "presentacion", "precio_publico"},
        "agregar_producto": {"nombre", "presentacion", "precio_publico"},
        "completar_alta": {"email"},
        "mi_stock": set(),
        "mi_resumen": {"semanas"},
        "mis_envios_abiertos": set(),
        "mis_liquidaciones": set(),
        "confirmar_envio": {"envio_id", "cantidad"},
        "rechazar_envio": {"envio_id"},
        "pedir_reposicion": {"producto_id", "cantidad"},
        "escalar": {"motivo", "resumen"},
        "responder_oferta_membresia": {"acepta"},
    }
    vistos = {accion.name for accion in m.actions}
    assert vistos == set(esperados), "una acción nueva o borrada no está en esta lista"
    for accion in m.actions:
        assert set(accion.parameters) == esperados[accion.name], (
            f"{accion.name} cambió sus parámetros"
        )


def test_toda_accion_con_handler_declara_writes():
    m = _lca()
    for accion in m.actions:
        if accion.handler:
            assert accion.writes is not None, f"{accion.name} no declara writes"


# --- Identidad -------------------------------------------------------------


@respx.mock
async def test_mi_ficha_resuelve_por_sender_phone_y_no_pide_a_quien():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    r = await _correr("mi_ficha")
    assert r.success
    assert r.data["identificado"] is True
    assert r.data["productor_id"] == PRODUCTOR
    pedido = respx.calls[0].request
    # Decodificado, no el string crudo de la URL: httpx manda el filtro
    # url-encoded (`+` sale `%2B`) y eso es lo correcto — `.url.params` lo
    # decodifica de vuelta, que es lo que importa comparar acá.
    assert pedido.url.params["filter"] == f"telefono:eq:{TELEFONO}"


@respx.mock
async def test_el_filtro_viaja_encodeado_y_no_como_un_espacio():
    """El caso que rompía en silencio: un `+` sin escapar en el query string
    decodifica del lado del servidor (Express + `qs`, que es lo que usa
    PRAXIS) como un ESPACIO, no como el signo. Si `_buscar` armara la URL a
    mano sin encodear el filtro, esta consulta no fallaría — simplemente no
    matchearía a ningún productor, y el síntoma sería indistinguible de "no
    está en el padrón". Se verifica sobre la URL cruda que salió realmente:
    lo que el servidor va a decodificar es `%2B`, nunca un `+` literal."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    await _correr("mi_ficha")
    cruda = str(respx.calls[0].request.url)
    assert "%2B5491155512345" in cruda
    assert "+5491155512345" not in cruda


@respx.mock
async def test_mi_ficha_lista_solo_los_productos_del_productor_de_la_sesion():
    """La tercera lista de la integración, con la misma regla que
    `mis_liquidaciones` y `mis_envios_abiertos`: sin este chequeo, apuntar el
    filtro a otro id (o borrarlo) no ponía rojo nada — el mock de
    `lca_producto` responde igual mande el filtro que mande."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    ruta = respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    await _correr("mi_ficha")
    assert ruta.calls[0].request.url.params["filter"] == f"productor:eq:{PRODUCTOR}"


@respx.mock
async def test_mi_ficha_no_lista_los_productos_dados_de_baja():
    """Un producto `activo: False` es uno que La Carta ya no vende. Ofrecérselo
    para reponer manda mercadería que va a quedar en el depósito."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto").mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {"id": "prod-1", "data": {"nombre": "Miel", "activo": True}},
                    {"id": "prod-2", "data": {"nombre": "Dulce viejo", "activo": False}},
                ],
                "total": 2,
            },
        )
    )
    r = await _correr("mi_ficha")
    assert [p["id"] for p in r.data["productos"]] == ["prod-1"]


@respx.mock
async def test_sin_sender_phone_no_identifica_a_nadie_y_no_lee_ningun_dato():
    ruta = respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    r = await _correr("mi_ficha", ctx={"channel": "telegram", "sender": "12345"})
    assert r.success is True
    assert r.data["identificado"] is False
    assert "productor_id" not in r.data
    assert not ruta.called, "no se consultó el padrón: no hay a quién buscar"


@respx.mock
async def test_un_telefono_dictado_en_los_argumentos_no_sirve_de_nada():
    """El ataque real medido en alcaldía: dictar el número de otro en el texto."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    r = await _correr("mi_ficha", {"telefono": "+5491199999999", "productor_id": "p-999"})
    assert respx.calls[0].request.url.params["filter"] == f"telefono:eq:{TELEFONO}"
    assert r.data["productor_id"] == PRODUCTOR


@respx.mock
async def test_dos_productores_con_el_mismo_telefono_cortan():
    respx.get(f"{BASE}/api/data/lca_productor").mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {"id": "p-1", "data": {"estado": "activo"}},
                    {"id": "p-2", "data": {"estado": "activo"}},
                ],
                "total": 2,
            },
        )
    )
    r = await _correr("mi_ficha")
    assert r.data["identificado"] is False


@respx.mock
async def test_un_productor_de_baja_no_se_identifica():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron(estado="baja"))
    r = await _correr("mi_ficha")
    assert r.data["identificado"] is False


@respx.mock
async def test_el_padron_se_pide_con_margen_sobre_el_guard_de_duplicados():
    """El guard de teléfono duplicado descarta las fichas de baja EN PYTHON,
    así que un `limit` justo lo esquiva: con tres fichas del mismo número —una
    de baja y dos activas— `limit=2` podía traer [baja, activa], dejar UNA fila
    y servirle la ficha a una de las dos que se disputan el teléfono. respx
    responde lo mismo mande el limit que mande, así que lo único que discrimina
    es el parámetro que viaja."""
    ruta = respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    await _correr("mi_ficha")
    assert int(ruta.calls[0].request.url.params["limit"]) >= 5


@respx.mock
async def test_mi_ficha_aprende_la_direccion_del_canal_cuando_cambia():
    """En Telegram la dirección NO es el teléfono, y el cron la necesita para
    escribirle. La escribe el handler desde el contexto, nunca el modelo."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron(direccion=""))
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    patch = respx.patch(f"{BASE}/api/data/lca_productor/{PRODUCTOR}").mock(
        return_value=httpx.Response(200, json={"id": PRODUCTOR, "data": {}})
    )
    await _correr("mi_ficha")
    assert patch.called
    assert patch.calls[0].request.read().decode().find("direccion_canal") != -1


@respx.mock
async def test_mi_ficha_no_se_rompe_si_guardar_la_direccion_del_canal_tira_una_excepcion():
    """La dirección del canal es un dato útil, no una precondición: un
    timeout al aprenderla no puede tumbar la ficha, que es lo único crítico
    de esta acción."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron(direccion=""))
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    respx.patch(f"{BASE}/api/data/lca_productor/{PRODUCTOR}").mock(
        side_effect=httpx.ConnectError("boom")
    )
    r = await _correr("mi_ficha")
    assert r.success is True
    assert r.data["identificado"] is True


@respx.mock
async def test_mi_ficha_no_se_rompe_si_guardar_la_direccion_del_canal_responde_500():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron(direccion=""))
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    respx.patch(f"{BASE}/api/data/lca_productor/{PRODUCTOR}").mock(
        return_value=httpx.Response(500, json={})
    )
    r = await _correr("mi_ficha")
    assert r.success is True
    assert r.data["identificado"] is True


# --- Oferta de membresía (spec §15.2) ---------------------------------------


def _pendiente(rows: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"rows": rows, "total": len(rows)})


def _pendiente_row(tipo: str, hace_dias: int) -> dict:
    fecha = (datetime.now(UTC) - timedelta(days=hace_dias)).date().isoformat()
    return {"id": f"pend-{tipo}-{hace_dias}", "created_at": fecha, "data": {"tipo": tipo}}


@respx.mock
async def test_un_productor_pago_nunca_recibe_la_oferta_de_membresia():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron(membresia="paga"))
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    pendientes = respx.get(f"{BASE}/api/data/lca_pendiente")
    r = await _correr("mi_ficha")
    assert r.data["puede_ofrecer_membresia"] is False
    assert not pendientes.called, "pago no necesita ni consultar la regla"


@respx.mock
async def test_un_no_reciente_bloquea_la_oferta_treinta_dias():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    respx.get(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=_pendiente([_pendiente_row("oferta_rechazada", hace_dias=10)])
    )
    r = await _correr("mi_ficha")
    assert r.data["puede_ofrecer_membresia"] is False


@respx.mock
async def test_dos_ofertas_en_el_trimestre_agotan_la_cuota():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    respx.get(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=_pendiente(
            [
                _pendiente_row("interes_membresia", hace_dias=80),
                _pendiente_row("interes_membresia", hace_dias=40),
            ]
        )
    )
    r = await _correr("mi_ficha")
    assert r.data["puede_ofrecer_membresia"] is False


@respx.mock
async def test_un_productor_limpio_recibe_la_oferta_de_membresia():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    respx.get(f"{BASE}/api/data/lca_pendiente").mock(return_value=_vacio())
    r = await _correr("mi_ficha")
    assert r.data["puede_ofrecer_membresia"] is True


@respx.mock
async def test_la_regla_de_oferta_mide_contra_el_reloj_de_handlers_y_no_contra_el_real(
    monkeypatch,
):
    """`_oferta_habilitada` re-importaba `datetime` DENTRO de la función, y ese
    import local tapaba el `monkeypatch.setattr(handlers, "datetime", …)` de
    `_instante_fijo`: el reloj congelado no congelaba nada y la ventana de 30
    días se medía contra la hora real de quien corre el test. Con el reloj en
    enero de 2026 un "no" del 10/1/2026 está a cinco días y bloquea; contra la
    hora real está a meses y no bloquearía, así que este caso distingue las dos
    cosas — los demás tests de la regla usan fechas relativas y no pueden."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    respx.get(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=_pendiente(
            [{"id": "p1", "created_at": "2026-01-10", "data": {"tipo": "oferta_rechazada"}}]
        )
    )
    _instante_fijo(monkeypatch, "2026-01-15T12:00:00+00:00")
    r = await _correr("mi_ficha")
    assert r.data["puede_ofrecer_membresia"] is False


@respx.mock
async def test_la_regla_de_oferta_acota_los_dos_tipos_en_la_query_y_no_en_python():
    """`lca_pendiente` acumula TAMBIÉN los escalamientos: traer los 50 primeros
    del productor para descartar casi todos en Python dejaba afuera las
    respuestas viejas apenas alguien escalara seguido, y la cuota del trimestre
    se calculaba sobre una muestra. Ordenar por fecha no es una alternativa
    acá: `lca_pendiente` no declara ningún campo de fecha de alta y `created_at`
    no es un campo declarado (sería un 422, no un orden ignorado)."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    ruta = respx.get(f"{BASE}/api/data/lca_pendiente").mock(return_value=_vacio())
    await _correr("mi_ficha")
    filtros = ruta.calls[0].request.url.params.get_list("filter")
    assert f"productor:eq:{PRODUCTOR}" in filtros
    assert "tipo:in:interes_membresia,oferta_rechazada" in filtros


# --- Alta -------------------------------------------------------------------


@respx.mock
async def test_corregir_un_producto_de_otro_productor_se_rechaza_sin_tocarlo():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto/ajeno").mock(
        return_value=httpx.Response(200, json={"id": "ajeno", "data": {"productor": "p-999"}})
    )
    patch = respx.patch(f"{BASE}/api/data/lca_producto/ajeno").mock(
        return_value=httpx.Response(200, json={})
    )
    r = await _correr("corregir_producto", {"producto_id": "ajeno", "precio_publico": 1})
    assert r.success is False
    assert not patch.called, "no se tocó nada de otro productor"
    # El mensaje del helper compartido `_suyo_o_fallo`, el mismo que dan las
    # otras cuatro acciones que reciben un id: un mensaje propio acá significa
    # que esta acción volvió a tener su propio camino de verificación.
    assert r.error == "eso no es tuyo o no existe"


@respx.mock
async def test_corregir_un_producto_inexistente_da_el_mismo_mensaje_que_uno_ajeno():
    """El comentario en `corregir_producto` afirma que "no existe" y "es de
    otro" comparten mensaje para no delatar qué ids existen. Sin este caso,
    separar los mensajes no pondría rojo nada."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto/no-existe").mock(
        return_value=httpx.Response(404, json={})
    )
    r = await _correr("corregir_producto", {"producto_id": "no-existe", "precio_publico": 1})
    assert r.success is False
    assert r.error == "eso no es tuyo o no existe"


@respx.mock
async def test_corregir_sin_id_falla_con_el_mensaje_del_helper_compartido():
    """`corregir_producto` es la 12va acción con id y pasa por el MISMO
    `_suyo_o_fallo` que las otras cuatro. Sin este caso, volver a darle un
    camino propio (`falta el id del producto`) no ponía rojo nada."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    ruta = respx.get(f"{BASE}/api/data/lca_producto/")
    r = await _correr("corregir_producto", {"producto_id": "  ", "precio_publico": 1})
    assert r.success is False
    assert r.error == "falta el id"
    assert not ruta.called


@respx.mock
async def test_corregir_lo_propio_anda():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto/mio").mock(
        return_value=httpx.Response(200, json={"id": "mio", "data": {"productor": PRODUCTOR}})
    )
    patch = respx.patch(f"{BASE}/api/data/lca_producto/mio").mock(
        return_value=httpx.Response(200, json={"id": "mio", "data": {"precio_publico": 4800}})
    )
    r = await _correr("corregir_producto", {"producto_id": "mio", "precio_publico": 4800})
    assert r.success is True
    assert patch.called


@respx.mock
async def test_agregar_producto_nace_con_sku_provisorio_y_lo_dice():
    """Sólo La Carta sabe con qué código lo vende Belgrano. El provisorio hace
    que sus ventas se rechacen con ese motivo hasta que lo carguen, en vez de
    aparear contra el producto equivocado."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    post = respx.post(f"{BASE}/api/data/lca_producto").mock(
        return_value=httpx.Response(201, json={"id": "nuevo", "data": {}})
    )
    r = await _correr(
        "agregar_producto",
        {"nombre": "Miel cremosa", "presentacion": "250g", "precio_publico": 3800},
    )
    assert r.success is True
    assert r.data["provisorio"] is True
    assert r.data["sku_externo"].startswith("pendiente:")
    cuerpo = json.loads(post.calls[0].request.content)
    assert cuerpo["productor"] == PRODUCTOR
    assert cuerpo["presentacion"] == "250g"
    assert cuerpo["precio_publico"] == 3800


@respx.mock
async def test_completar_alta_activa_y_guarda_el_mail():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron(estado="precargado"))
    patch = respx.patch(f"{BASE}/api/data/lca_productor/{PRODUCTOR}").mock(
        return_value=httpx.Response(200, json={"id": PRODUCTOR, "data": {"estado": "activo"}})
    )
    r = await _correr("completar_alta", {"email": "juan@mieldeltalar.com.ar"})
    assert r.success is True
    cuerpo = json.loads(patch.calls[-1].request.content)
    assert cuerpo["estado"] == "activo"
    assert cuerpo["email"] == "juan@mieldeltalar.com.ar"


# --- Consultas --------------------------------------------------------------


def _funcion(resultado):
    return httpx.Response(200, json={"value": resultado})


@respx.mock
async def test_mi_stock_llama_a_la_funcion_con_el_productor_de_la_sesion():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    fn = respx.post(f"{BASE}/api/functions/lca_stock_y_proyeccion").mock(
        return_value=_funcion(
            {"productos": [{"producto_id": "x", "en_gondola": 24, "dias_cobertura": 18.6}]}
        )
    )
    r = await _correr("mi_stock", {"productor_id": "p-999"})
    assert r.success is True
    cuerpo = fn.calls[0].request.read().decode()
    assert PRODUCTOR in cuerpo
    assert "p-999" not in cuerpo


@respx.mock
async def test_mis_liquidaciones_no_devuelve_borradores():
    """Un borrador es un número que La Carta todavía no aprobó. Que llegue al
    productor sería prometerle una plata que puede cambiar."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_liquidacion").mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {
                        "id": "l-1",
                        "data": {"periodo": "2026-08", "estado": "borrador", "neto": 100},
                    },
                    {
                        "id": "l-2",
                        "data": {"periodo": "2026-07", "estado": "aprobada", "neto": 200},
                    },
                    {
                        "id": "l-3",
                        "data": {"periodo": "2026-06", "estado": "acreditada", "neto": 300},
                    },
                ],
                "total": 3,
            },
        )
    )
    r = await _correr("mis_liquidaciones")
    periodos = [x["periodo"] for x in r.data["liquidaciones"]]
    assert periodos == ["2026-07", "2026-06"]


@respx.mock
async def test_mis_liquidaciones_filtra_por_el_productor_de_la_sesion():
    """Sin este chequeo, `productor:eq:{id}` se podía borrar o apuntar a otro
    id y ningún test se ponía rojo: el mock de respx devuelve el mismo
    payload sin importar qué filtro viajó."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    ruta = respx.get(f"{BASE}/api/data/lca_liquidacion").mock(return_value=_vacio())
    await _correr("mis_liquidaciones")
    assert ruta.calls[0].request.url.params["filter"] == f"productor:eq:{PRODUCTOR}"


@respx.mock
async def test_mis_liquidaciones_pide_las_mas_recientes_primero():
    """Sin `sort`, pasadas las 50 filas PRAXIS devuelve las que quiera ("whatever
    order Postgres feels like") y a un productor viejo se le contestaría con las
    liquidaciones de hace dos años. respx responde lo mismo con orden o sin él:
    lo único que discrimina es el parámetro que viaja. `periodo` es `AAAA-MM`,
    así que el orden lexicográfico ES el cronológico."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    ruta = respx.get(f"{BASE}/api/data/lca_liquidacion").mock(return_value=_vacio())
    await _correr("mis_liquidaciones")
    assert ruta.calls[0].request.url.params["sort"] == "periodo:desc"


@respx.mock
async def test_mis_envios_abiertos_trae_los_propuestos_y_confirmados_del_que_escribe():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto").mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {
                        "id": "prod-1",
                        "data": {
                            "nombre": "Miel de eucalipto",
                            "presentacion": "500g",
                            "productor": PRODUCTOR,
                        },
                    }
                ],
                "total": 1,
            },
        )
    )
    respx.get(f"{BASE}/api/data/lca_envio").mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {
                        "id": "e-1",
                        "data": {
                            "producto": "prod-1",
                            "estado": "propuesto",
                            "cantidad_sugerida": 12,
                        },
                    },
                    {
                        "id": "e-2",
                        "data": {
                            "producto": "ajeno",
                            "estado": "propuesto",
                            "cantidad_sugerida": 5,
                        },
                    },
                ],
                "total": 2,
            },
        )
    )
    r = await _correr("mis_envios_abiertos")
    assert [e["envio_id"] for e in r.data["envios"]] == ["e-1"]
    assert r.data["envios"][0]["producto"] == "Miel de eucalipto"


@respx.mock
async def test_mis_envios_abiertos_filtra_los_productos_por_el_productor_de_la_sesion():
    """`lca_envio` viene SIN scoping del lado de PRAXIS: el mapa de productos
    propios es lo único que separa un envío mío de uno ajeno, y ese mapa sale
    de este filtro. Sin este chequeo, apuntarlo a otro productor (o borrarlo)
    no ponía rojo nada — el mock de `lca_producto` responde igual."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    ruta = respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    respx.get(f"{BASE}/api/data/lca_envio").mock(return_value=_vacio())
    await _correr("mis_envios_abiertos")
    assert ruta.calls[0].request.url.params["filter"] == f"productor:eq:{PRODUCTOR}"


@respx.mock
async def test_mis_envios_abiertos_pide_los_dos_filtros_y_no_recorta_en_python():
    """El aislamiento viaja en la QUERY, no en el `if` de después: traer los
    abiertos de TODO el tenant con `limit=200` y recortarlos acá se comía un
    envío propio apenas los 300 productores pasaran las 200 filas abiertas, y
    el síntoma era el agente contestando "no tenés nada pendiente" al productor
    que acababa de decir que sí. Los DOS filtros tienen que llegar: con uno
    solo, PRAXIS devuelve de más o de menos y nada falla."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto").mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {"id": "prod-1", "data": {"nombre": "Miel"}},
                    {"id": "prod-2", "data": {"nombre": "Dulce"}},
                ],
                "total": 2,
            },
        )
    )
    ruta = respx.get(f"{BASE}/api/data/lca_envio").mock(return_value=_vacio())
    await _correr("mis_envios_abiertos")
    filtros = ruta.calls[0].request.url.params.get_list("filter")
    assert "estado:in:propuesto,confirmado" in filtros
    assert "producto:in:prod-1,prod-2" in filtros


@respx.mock
async def test_mis_envios_abiertos_sin_productos_no_consulta_los_envios():
    """El borde del filtro de arriba: sin productos propios, `producto:in:`
    quedaría VACÍO y esa consulta no filtra por producto — traería los envíos
    abiertos de todo el tenant. Sin productos tampoco puede haber un envío
    suyo, así que se corta antes."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    ruta = respx.get(f"{BASE}/api/data/lca_envio").mock(return_value=_vacio())
    r = await _correr("mis_envios_abiertos")
    assert r.success is True
    assert r.data["envios"] == []
    assert not ruta.called


# --- mi_resumen --------------------------------------------------------------


@respx.mock
async def test_mi_resumen_recorta_semanas_al_piso():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    fn = respx.post(f"{BASE}/api/functions/lca_reporte_semanal").mock(
        return_value=_funcion({"unidades": 1})
    )
    r = await _correr("mi_resumen", {"semanas": 0})
    assert r.success is True
    assert len(fn.calls) == 1


@respx.mock
async def test_mi_resumen_recorta_semanas_al_techo():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    fn = respx.post(f"{BASE}/api/functions/lca_reporte_semanal").mock(
        return_value=_funcion({"unidades": 1})
    )
    r = await _correr("mi_resumen", {"semanas": 100})
    assert r.success is True
    assert len(fn.calls) == 8


@respx.mock
async def test_mi_resumen_llama_una_vez_por_semana_pedida():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    fn = respx.post(f"{BASE}/api/functions/lca_reporte_semanal").mock(
        return_value=_funcion({"unidades": 1})
    )
    r = await _correr("mi_resumen", {"semanas": 3})
    assert r.success is True
    assert len(fn.calls) == 3
    cuerpos = [json.loads(c.request.content)["args"] for c in fn.calls]
    assert all(c["productor"] == PRODUCTOR for c in cuerpos)
    fechas = [c["desde"] for c in cuerpos]
    assert len(set(fechas)) == 3, "cada semana pedida tiene que traer un `desde` distinto"


@respx.mock
async def test_mi_resumen_calcula_la_semana_en_la_zona_de_argentina_y_no_en_utc(monkeypatch):
    """Domingo 30/8 a las 23:30 en Argentina (UTC-3) ya es lunes 31/8 02:30 en
    UTC. Si `mi_resumen` calculara "hoy" en UTC, tomaría el lunes siguiente
    como el de la semana en curso y pediría una semana entera más tarde de lo
    que la persona considera "la semana pasada"."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    fn = respx.post(f"{BASE}/api/functions/lca_reporte_semanal").mock(
        return_value=_funcion({"unidades": 1})
    )
    _instante_fijo(monkeypatch, "2026-08-31T02:30:00+00:00")
    await _correr("mi_resumen")
    cuerpo = json.loads(fn.calls[0].request.content)["args"]
    assert cuerpo["desde"] == "2026-08-17"


# --- Envíos ------------------------------------------------------------------


@respx.mock
async def test_confirmar_un_envio_ajeno_no_llama_a_la_funcion():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_envio/e-otro").mock(
        return_value=httpx.Response(200, json={"id": "e-otro", "data": {"producto": "prod-otro"}})
    )
    respx.get(f"{BASE}/api/data/lca_producto/prod-otro").mock(
        return_value=httpx.Response(200, json={"id": "prod-otro", "data": {"productor": "p-999"}})
    )
    fn = respx.post(f"{BASE}/api/functions/lca_confirmar_envio").mock(
        return_value=_funcion({"envio": {}})
    )
    r = await _correr("confirmar_envio", {"envio_id": "e-otro", "cantidad": 20})
    assert r.success is False
    assert not fn.called
    assert r.error == "eso no es tuyo o no existe"


@respx.mock
async def test_confirmar_lo_propio_pasa_la_cantidad_que_dijo_el_productor():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_envio/e-1").mock(
        return_value=httpx.Response(200, json={"id": "e-1", "data": {"producto": "prod-1"}})
    )
    respx.get(f"{BASE}/api/data/lca_producto/prod-1").mock(
        return_value=httpx.Response(200, json={"id": "prod-1", "data": {"productor": PRODUCTOR}})
    )
    fn = respx.post(f"{BASE}/api/functions/lca_confirmar_envio").mock(
        return_value=_funcion({"envio": {"id": "e-1", "estado": "confirmado", "cantidad": 20}})
    )
    r = await _correr("confirmar_envio", {"envio_id": "e-1", "cantidad": 20})
    assert r.success is True
    # httpx serializa el JSON compacto (`separators=(",", ":")`), sin espacio
    # después de los dos puntos: comparar la forma exacta rompería contra ese
    # detalle de encoding en vez de contra el dato que importa.
    cuerpo = json.loads(fn.calls[0].request.read().decode())["args"]
    assert cuerpo == {"envio": "e-1", "cantidad": 20}


@respx.mock
async def test_una_cantidad_bajo_el_lote_minimo_vuelve_con_el_motivo_y_no_rompe():
    """PRAXIS rechaza con 422 y el mensaje dice cuál es el lote mínimo. El
    agente tiene que poder contárselo, así que el error viaja completo."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_envio/e-1").mock(
        return_value=httpx.Response(200, json={"id": "e-1", "data": {"producto": "prod-1"}})
    )
    respx.get(f"{BASE}/api/data/lca_producto/prod-1").mock(
        return_value=httpx.Response(200, json={"id": "prod-1", "data": {"productor": PRODUCTOR}})
    )
    respx.post(f"{BASE}/api/functions/lca_confirmar_envio").mock(
        return_value=httpx.Response(422, text="El lote mínimo de ese producto es 6.")
    )
    r = await _correr("confirmar_envio", {"envio_id": "e-1", "cantidad": 2})
    assert r.success is False
    assert "lote mínimo" in (r.error or "")
    assert r.error.endswith("El lote mínimo de ese producto es 6.")


@respx.mock
async def test_confirmar_envio_sin_id_falla_sin_consultar_nada():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    r = await _correr("confirmar_envio", {"envio_id": "", "cantidad": 5})
    assert r.success is False
    assert r.error == "falta el id"


@respx.mock
async def test_confirmar_envio_sin_cantidad_se_rechaza_sin_invocar_a_praxis():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_envio/e-1").mock(
        return_value=httpx.Response(200, json={"id": "e-1", "data": {"producto": "prod-1"}})
    )
    respx.get(f"{BASE}/api/data/lca_producto/prod-1").mock(
        return_value=httpx.Response(200, json={"id": "prod-1", "data": {"productor": PRODUCTOR}})
    )
    fn = respx.post(f"{BASE}/api/functions/lca_confirmar_envio").mock(
        return_value=_funcion({"envio": {}})
    )
    r = await _correr("confirmar_envio", {"envio_id": "e-1"})
    assert r.success is False
    assert r.error == "falta la cantidad"
    assert not fn.called


@respx.mock
async def test_rechazar_un_envio_ajeno_no_llama_a_la_funcion():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_envio/e-otro").mock(
        return_value=httpx.Response(200, json={"id": "e-otro", "data": {"producto": "prod-otro"}})
    )
    respx.get(f"{BASE}/api/data/lca_producto/prod-otro").mock(
        return_value=httpx.Response(200, json={"id": "prod-otro", "data": {"productor": "p-999"}})
    )
    fn = respx.post(f"{BASE}/api/functions/lca_rechazar_envio").mock(
        return_value=_funcion({"envio": {}})
    )
    r = await _correr("rechazar_envio", {"envio_id": "e-otro"})
    assert r.success is False
    assert not fn.called
    assert r.error == "eso no es tuyo o no existe"


@respx.mock
async def test_rechazar_lo_propio_cierra_ese_envio_y_ninguno_mas():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_envio/e-1").mock(
        return_value=httpx.Response(200, json={"id": "e-1", "data": {"producto": "prod-1"}})
    )
    respx.get(f"{BASE}/api/data/lca_producto/prod-1").mock(
        return_value=httpx.Response(200, json={"id": "prod-1", "data": {"productor": PRODUCTOR}})
    )
    fn = respx.post(f"{BASE}/api/functions/lca_rechazar_envio").mock(
        return_value=_funcion({"envio": {"id": "e-1", "estado": "rechazado"}})
    )
    r = await _correr("rechazar_envio", {"envio_id": "e-1"})
    assert r.success is True
    assert json.loads(fn.calls[0].request.read().decode())["args"] == {"envio": "e-1"}


@respx.mock
async def test_pedir_reposicion_de_un_producto_ajeno_se_rechaza():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto/ajeno").mock(
        return_value=httpx.Response(200, json={"id": "ajeno", "data": {"productor": "p-999"}})
    )
    fn = respx.post(f"{BASE}/api/functions/lca_pedir_reposicion").mock(
        return_value=_funcion({"envio": {}})
    )
    r = await _correr("pedir_reposicion", {"producto_id": "ajeno", "cantidad": 12})
    assert r.success is False
    assert not fn.called


@respx.mock
async def test_pedir_reposicion_de_lo_propio_manda_producto_y_cantidad():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto/prod-1").mock(
        return_value=httpx.Response(200, json={"id": "prod-1", "data": {"productor": PRODUCTOR}})
    )
    fn = respx.post(f"{BASE}/api/functions/lca_pedir_reposicion").mock(
        return_value=_funcion({"envio": {"id": "e-9", "estado": "confirmado"}})
    )
    r = await _correr("pedir_reposicion", {"producto_id": "prod-1", "cantidad": 12})
    assert r.success is True
    assert json.loads(fn.calls[0].request.read().decode())["args"] == {
        "producto": "prod-1",
        "cantidad": 12,
    }


@respx.mock
async def test_pedir_reposicion_sin_cantidad_se_rechaza_sin_invocar_a_praxis():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto/prod-1").mock(
        return_value=httpx.Response(200, json={"id": "prod-1", "data": {"productor": PRODUCTOR}})
    )
    fn = respx.post(f"{BASE}/api/functions/lca_pedir_reposicion").mock(
        return_value=_funcion({"envio": {}})
    )
    r = await _correr("pedir_reposicion", {"producto_id": "prod-1"})
    assert r.success is False
    assert r.error == "falta la cantidad"
    assert not fn.called


# --- Pendientes y membresía -------------------------------------------------


@respx.mock
async def test_escalar_sin_identidad_abre_el_pendiente_con_el_telefono_del_canal():
    """La única acción que corre sin identificar a nadie: es exactamente el caso
    de alguien que dice ser productor y no está en el padrón."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_vacio())
    respx.get(f"{BASE}/api/data/lca_pendiente").mock(return_value=_vacio())
    post = respx.post(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=httpx.Response(201, json={"id": "pend-1", "data": {}})
    )
    r = await _correr(
        "escalar", {"motivo": "telefono_desconocido", "resumen": "Dice que es productor"}
    )
    assert r.success is True
    cuerpo = post.calls[0].request.read().decode()
    assert TELEFONO in cuerpo
    assert "telefono_desconocido" in cuerpo


@respx.mock
async def test_escalar_ignora_un_telefono_dictado_en_los_argumentos():
    """El docstring de `escalar` promete que el teléfono sale del CANAL: si
    viniera del modelo, cualquiera podría llenar la bandeja de La Carta con
    números ajenos. El invariante de los PARÁMETROS no alcanza para fijarlo —
    el executor le pasa al handler el dict de argumentos SIN filtrar
    (`executor.py:_with_defaults` copia todo), así que un handler que lee una
    clave no declarada le es invisible."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_vacio())
    dedupe = respx.get(f"{BASE}/api/data/lca_pendiente").mock(return_value=_vacio())
    post = respx.post(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=httpx.Response(201, json={"id": "pend-9", "data": {}})
    )
    r = await _correr(
        "escalar",
        {
            "motivo": "telefono_desconocido",
            "resumen": "x",
            "telefono": "+5491199999999",
        },
    )
    assert r.success is True
    cuerpo = json.loads(post.calls[0].request.content)
    assert cuerpo["telefono"] == TELEFONO
    assert "+5491199999999" not in post.calls[0].request.read().decode()
    # Y el dedupe busca por el número del canal, no por el dictado: buscar por
    # el ajeno abriría un pendiente nuevo cada vez.
    assert f"telefono:eq:{TELEFONO}" in dedupe.calls[0].request.url.params.get_list("filter")


@respx.mock
async def test_escalar_no_confunde_un_padron_caido_con_un_telefono_desconocido():
    """Es la única acción que distingue "no está en el padrón" de "el padrón no
    contestó", y la distinción viene gratis: `_sin_identidad()` viaja con
    `success=True` y un HTTP 500 con `success=False`. Tragarse el segundo abría
    un pendiente de "teléfono desconocido" para alguien que SÍ está en el
    padrón — basura que una persona de La Carta tiene que atender."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=httpx.Response(500, text="boom"))
    post = respx.post(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=httpx.Response(201, json={})
    )
    r = await _correr("escalar", {"motivo": "telefono_desconocido", "resumen": "x"})
    assert r.success is False
    assert "consultar lca_productor falló" in (r.error or "")
    assert not post.called, "con el padrón caído no se abre ningún pendiente"


@respx.mock
async def test_escalar_sin_telefono_en_el_canal_no_crea_un_pendiente_ciego():
    """Sin productor y sin teléfono el pendiente no tiene por dónde volver:
    nadie de La Carta puede atender un "alguien dice ser productor" sin número
    ni ficha. Y el dedupe es POR teléfono, así que sin él cada llamada desde el
    banco de pruebas dejaba una fila más, indistinguible de la anterior."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_vacio())
    post = respx.post(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=httpx.Response(201, json={})
    )
    r = await _correr(
        "escalar",
        {"motivo": "telefono_desconocido", "resumen": "x"},
        ctx={"channel": "telegram", "sender": "12345"},
    )
    assert r.success is True
    assert r.data["identificado"] is False
    assert not post.called


@respx.mock
async def test_escalar_dos_veces_el_mismo_telefono_no_abre_dos_pendientes():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_vacio())
    respx.get(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {
                        "id": "pend-1",
                        "data": {
                            "tipo": "telefono_desconocido",
                            "estado": "abierto",
                            "telefono": TELEFONO,
                        },
                    }
                ],
                "total": 1,
            },
        )
    )
    post = respx.post(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=httpx.Response(201, json={})
    )
    r = await _correr("escalar", {"motivo": "telefono_desconocido", "resumen": "otra vez"})
    assert r.success is True
    assert not post.called
    # El dedupe descansa ENTERO en la query: acotar el tipo y el estado en
    # Python sobre las 20 primeras filas del teléfono se saltea el duplicado en
    # cuanto hay veinte pendientes viejos, y `lca_pendiente` no tiene campo de
    # fecha por el que ordenar para quedarse con los últimos. El mock devuelve
    # la misma fila mande el filtro que mande, así que lo que discrimina es
    # esto.
    filtros = respx.calls[1].request.url.params.get_list("filter")
    assert f"telefono:eq:{TELEFONO}" in filtros
    assert "tipo:eq:telefono_desconocido" in filtros
    assert "estado:eq:abierto" in filtros


@respx.mock
async def test_escalar_con_motivo_desconocido_se_rechaza_sin_consultar_nada():
    """La validación de `motivo` corta ANTES de resolver identidad: ningún
    endpoint se llega a consultar. Si no fuera así, este test pasaría igual
    por cualquier otra falla (por ejemplo una ruta sin mockear), sin decir
    nada sobre el chequeo real."""
    ruta = respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_vacio())
    r = await _correr("escalar", {"motivo": "invento", "resumen": "algo"})
    assert r.success is False
    assert "motivo desconocido" in (r.error or "")
    assert not ruta.called


@respx.mock
async def test_escalar_identificado_por_otro_motivo_manda_el_id_del_productor():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    post = respx.post(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=httpx.Response(201, json={"id": "pend-3", "data": {}})
    )
    r = await _correr("escalar", {"motivo": "liquidacion", "resumen": "no le cerró un número"})
    assert r.success is True
    cuerpo = json.loads(post.calls[0].request.content)
    assert cuerpo["productor"] == PRODUCTOR
    assert cuerpo["tipo"] == "escalamiento"


@respx.mock
async def test_un_no_a_la_membresia_apaga_la_oferta_por_30_dias():
    ayer = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    respx.get(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [{"id": "p1", "created_at": ayer, "data": {"tipo": "oferta_rechazada"}}],
                "total": 1,
            },
        )
    )
    r = await _correr("mi_ficha")
    assert r.data["puede_ofrecer_membresia"] is False


@respx.mock
async def test_un_productor_pago_nunca_recibe_la_oferta_bis():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron(membresia="paga"))
    respx.get(f"{BASE}/api/data/lca_producto").mock(return_value=_vacio())
    r = await _correr("mi_ficha")
    assert r.data["puede_ofrecer_membresia"] is False


@respx.mock
async def test_dos_sies_seguidos_a_la_membresia_no_abren_dos_pendientes():
    """Mismo dedupe que `escalar` y por lo mismo: dos "sí" en la misma
    conversación son DOS ítems para que La Carta llame a la misma persona por
    lo mismo."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    ruta = respx.get(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=_pendiente(
            [{"id": "p-1", "data": {"tipo": "interes_membresia", "estado": "abierto"}}]
        )
    )
    post = respx.post(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=httpx.Response(201, json={})
    )
    r = await _correr("responder_oferta_membresia", {"acepta": True})
    assert r.success is True
    assert r.data["ya_estaba"] is True
    assert not post.called
    filtros = ruta.calls[0].request.url.params.get_list("filter")
    assert f"productor:eq:{PRODUCTOR}" in filtros
    assert "tipo:eq:interes_membresia" in filtros
    assert "estado:eq:abierto" in filtros


@respx.mock
async def test_un_no_a_la_membresia_se_registra_siempre_y_no_se_deduplica():
    """El dedupe es SÓLO del "sí". Un "no" nace `resuelto` y no entra a ninguna
    bandeja, y la regla de §15.2 cuenta esas filas: deduplicarlas le regalaría
    cuota a quien dice que no dos veces."""
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    ruta = respx.get(f"{BASE}/api/data/lca_pendiente").mock(return_value=_vacio())
    post = respx.post(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=httpx.Response(201, json={})
    )
    r = await _correr("responder_oferta_membresia", {"acepta": False})
    assert r.success is True
    assert r.data["ya_estaba"] is False
    assert post.called
    assert not ruta.called, "un `no` no consulta la bandeja: se registra siempre"


@respx.mock
async def test_aceptar_la_oferta_abre_un_pendiente_para_la_bandeja():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/lca_pendiente").mock(return_value=_vacio())
    post = respx.post(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=httpx.Response(201, json={"id": "pend-2", "data": {}})
    )
    r = await _correr("responder_oferta_membresia", {"acepta": True})
    assert r.success is True
    cuerpo = post.calls[0].request.read().decode()
    assert "interes_membresia" in cuerpo
    # httpx serializa compacto (`separators=(",", ":")`), sin espacio tras los
    # dos puntos.
    assert '"estado":"abierto"' in cuerpo


@respx.mock
async def test_rechazar_la_oferta_queda_resuelto_y_no_en_la_bandeja():
    respx.get(f"{BASE}/api/data/lca_productor").mock(return_value=_padron())
    post = respx.post(f"{BASE}/api/data/lca_pendiente").mock(
        return_value=httpx.Response(201, json={"id": "pend-4", "data": {}})
    )
    r = await _correr("responder_oferta_membresia", {"acepta": False})
    assert r.success is True
    cuerpo = json.loads(post.calls[0].request.content)
    assert cuerpo["tipo"] == "oferta_rechazada"
    assert cuerpo["estado"] == "resuelto"
