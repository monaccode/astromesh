"""El vertical de recaudación municipal, y el único del catálogo que existe por
una razón de SEGURIDAD y no de ergonomía.

Sus hermanos (`praxis_cobranzas`, `praxis_inmobiliaria`) envuelven funciones de
PRAXIS para que el agente tenga tools legibles. Éste además CIERRA un agujero:
con la tool genérica `buscar_records`, el teléfono por el que se busca al
contribuyente es un argumento que escribe el modelo, y un número dictado en el
texto del mensaje alcanzaba para servir la cuenta de un tercero — medido en dev
el 2026-08-31 con la vertical `alcaldia` de CLARUS.

Por eso los tests que más valen acá no son los de forma: son los que prueban
que **no hay forma de pedir la cuenta de otro**, ni por parámetro ni por
sesión falsa.

Los tests de forma (nombres válidos, placeholders declarados, un modo por
acción) los hereda de `test_integration_conformance.py`, parametrizado sobre
todo el catálogo.
"""

import httpx
import respx

from astromesh.integrations import IntegrationCatalog
from astromesh.integrations.catalog.praxis_alcaldia.handlers import telefono_de_sesion
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor

BASE = "https://erp.elhatillo.gob.ve"
TELEFONO = "+584141234567"
# El session_id REAL que llega al runtime, medido en dev el 2026-09-01 leyendo
# el span `agent.run` de una invocación: Herald arma `whatsapp__+58…` y Nexus le
# antepone SU espacio de nombres antes de pasarlo. Los tests usan éste y no el
# de Herald a secas, porque la primera versión del parser partía por el primer
# `__` —pasaba con el de Herald y fallaba con TODOS los reales—.
SESION = f"t_tenant-e07042fe-4994-409b-bff0-ba5eb68a6466__suhat-tributos__whatsapp__{TELEFONO}"
CONTRIBUYENTE = "c-1"


def _alc():
    catalog = IntegrationCatalog()
    catalog.discover()
    return catalog.get("praxis_alcaldia")


def _conn():
    return ResolvedConnection(name="praxis", material={"api_key": "praxis_K"}, base_url=BASE)


async def _correr(accion: str, args: dict, session_id: str = SESION, ctx: dict | None = None):
    m = _alc()
    return await HttpActionExecutor().execute(
        m,
        m.action(accion),
        args,
        _conn(),
        agent_name="tributos",
        session_id=session_id,
        caller_context=ctx,
    )


def _padron(activo: bool = True):
    return httpx.Response(
        200,
        json={
            "rows": [
                {
                    "id": CONTRIBUYENTE,
                    "data": {"nombre": "La Boyera C.A.", "rif": "J-410258963", "activo": activo},
                }
            ],
            "total": 1,
        },
    )


def _liquidaciones(rows=None):
    return httpx.Response(200, json={"rows": rows if rows is not None else [], "total": 0})


def _tasa(valor=322.75, fecha="2026-09-01"):
    return httpx.Response(
        200, json={"rows": [{"id": "t-1", "data": {"fecha": fecha, "valor_bs": valor}}], "total": 1}
    )


# --------------------------------------------------------------------------
# Forma
# --------------------------------------------------------------------------


def test_no_trae_base_url_propio():
    """Igual que `praxis`: un default le pegaría al ERP equivocado en silencio."""
    assert _alc().base_url is None


def test_expone_exactamente_las_tres_acciones():
    assert {a.name for a in _alc().actions} == {
        "mi_cuenta",
        "consultar_clasificador",
        "informar_pago",
    }


def test_comparte_la_credencial_de_maquina_con_praxis():
    m = _alc()
    assert m.auth.scheme == "bearer"
    assert m.auth.credential == "api_key"


def test_solo_informar_pago_declara_writes():
    """`writes` es lo ÚNICO que esta capa puede decir sobre la escritura.

    El gate de confirmación NO vive acá: `confirm` es un campo de
    `spec.tools[].confirm` en el manifiesto del agente, y el manifest de una
    integración lo rechaza como campo desconocido — verificado poniéndolo y
    viendo al catálogo saltear la integración entera. Quien tiene que declarar
    el gate es la plantilla de la centuria que declara esta tool.
    """
    acciones = {a.name: a for a in _alc().actions}
    assert acciones["informar_pago"].writes is True
    assert not acciones["mi_cuenta"].writes
    assert not acciones["consultar_clasificador"].writes


def test_mi_cuenta_no_declara_ningun_parametro():
    """El test central de todo este manifest.

    En cuanto `mi_cuenta` acepte un parámetro de identidad —un teléfono, un
    RIF, un id de contribuyente— el modelo puede llenarlo con lo que le
    dicten, y volvemos exactamente al agujero que esta integración existe para
    cerrar. Que la lista esté vacía NO es una simplificación: es el límite.
    """
    assert _alc().action("mi_cuenta").parameters == {}


# --------------------------------------------------------------------------
# La identidad: de dónde sale y qué pasa cuando no está
# --------------------------------------------------------------------------


def test_el_telefono_sale_del_session_id_prefijado_por_nexus():
    """El caso que rompió en dev: Nexus antepone tenant y agente.

    Herald arma `<canal>__<usuario>`
    (`astromesh-herald/internal/domain/conversation.go:26-28`) pero eso NO es lo
    que llega al runtime. Leer desde el primer `__` da un "canal" que es el
    tenant, y la identidad falla para todo el mundo — incluido el contribuyente
    legítimo, que es exactamente lo que pasó el 2026-09-01.
    """
    assert telefono_de_sesion(SESION) == TELEFONO
    # Y el de Herald a secas también, por si alguna vez llega sin prefijo.
    assert telefono_de_sesion(f"whatsapp__{TELEFONO}") == TELEFONO


def test_una_sesion_que_no_identifica_a_nadie_devuelve_none():
    casos = [
        "",  # sin sesión
        "prueba-mths8cm3-bullje-tributos",  # el banco de pruebas de Centuria
        "t_tenant-x__prueba-mths8cm3-bullje-tributos",  # el mismo, prefijado
        "t_tenant-x__ag__telegram__123456789",  # un id de chat NO es un teléfono
        "t_tenant-x__ag__instagram__17841400000000000",  # ni un id de Instagram
        "t_tenant-x__ag__whatsapp__no-es-un-numero",
        "t_tenant-x__ag__whatsapp__584141234567",  # sin el '+'
    ]
    for caso in casos:
        assert telefono_de_sesion(caso) is None, caso


@respx.mock
async def test_mi_cuenta_busca_por_el_telefono_de_la_sesion_y_no_por_uno_dictado():
    """Aunque el modelo mande argumentos con otro número, se ignoran enteros.

    Es la prueba de que el agujero está cerrado por construcción: no hay
    camino desde un argumento hasta el filtro que consulta el padrón.
    """
    padron = respx.get(f"{BASE}/api/data/alc_contribuyente").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/alc_liquidacion").mock(return_value=_liquidaciones())
    respx.get(f"{BASE}/api/data/alc_tasa_cambio").mock(return_value=_tasa())

    res = await _correr(
        "mi_cuenta",
        {"telefono": "+584149999999", "rif": "J-999", "contribuyente_id": "c-999"},
    )

    assert res.success
    assert res.data["identificado"] is True
    consultado = padron.calls[0].request.url.params["filter"]
    assert consultado == f"telefono:eq:{TELEFONO}"
    assert "584149999999" not in str(padron.calls[0].request.url)


@respx.mock
async def test_sin_sesion_util_no_consulta_nada_y_lo_explica():
    """Falla cerrado: ni una llamada al padrón.

    Es lo que pasa en el banco de pruebas de Centuria, y también en Instagram
    o Telegram. Devolver algo ahí sería devolver la cuenta de alguien a quien
    nadie identificó.
    """
    padron = respx.get(f"{BASE}/api/data/alc_contribuyente").mock(return_value=_padron())

    res = await _correr("mi_cuenta", {}, session_id="t_tenant-x__ag__prueba-mths8cm3-bullje")

    assert res.success  # no es un error del sistema: es un dato de la conversación
    assert res.data["identificado"] is False
    assert "registrado" in res.data["motivo"]
    assert padron.call_count == 0


@respx.mock
async def test_un_telefono_que_no_esta_en_el_padron_no_identifica_a_nadie():
    respx.get(f"{BASE}/api/data/alc_contribuyente").mock(
        return_value=httpx.Response(200, json={"rows": [], "total": 0})
    )
    res = await _correr("mi_cuenta", {})
    assert res.data["identificado"] is False


@respx.mock
async def test_un_contribuyente_dado_de_baja_tampoco():
    """`activo: false` sale del padrón: la cuenta de alguien dado de baja no se
    muestra por el hecho de conservar el número."""
    respx.get(f"{BASE}/api/data/alc_contribuyente").mock(return_value=_padron(activo=False))
    res = await _correr("mi_cuenta", {})
    assert res.data["identificado"] is False


# --------------------------------------------------------------------------
# Lo que devuelve
# --------------------------------------------------------------------------


@respx.mock
async def test_mi_cuenta_dice_si_esta_solvente_y_saca_las_anuladas():
    respx.get(f"{BASE}/api/data/alc_contribuyente").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/alc_liquidacion").mock(
        return_value=_liquidaciones(
            [
                {"id": "l-1", "data": {"estado": "pendiente", "monto_uc": 12.5}},
                {"id": "l-2", "data": {"estado": "pagada", "monto_uc": 8}},
                {"id": "l-3", "data": {"estado": "anulada", "monto_uc": 99}},
            ]
        )
    )
    respx.get(f"{BASE}/api/data/alc_tasa_cambio").mock(return_value=_tasa())
    res = await _correr("mi_cuenta", {})

    ids = [x["id"] for x in res.data["liquidaciones"]]
    # La anulada no se debe: mostrarla haría que la persona crea que debe algo.
    assert ids == ["l-1", "l-2"]
    # La pagada SÍ viaja: "¿estoy solvente?" es media consulta de taquilla.
    assert res.data["solvente"] is False


@respx.mock
async def test_sin_liquidaciones_pendientes_esta_solvente():
    respx.get(f"{BASE}/api/data/alc_contribuyente").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/alc_liquidacion").mock(
        return_value=_liquidaciones([{"id": "l-2", "data": {"estado": "pagada"}}])
    )
    respx.get(f"{BASE}/api/data/alc_tasa_cambio").mock(return_value=_tasa())
    res = await _correr("mi_cuenta", {})
    assert res.data["solvente"] is True


@respx.mock
async def test_mi_cuenta_trae_la_tasa_con_su_fecha_en_la_misma_llamada():
    """Sin la tasa, el agente no puede pasar de unidades de cuenta a bolívares
    — y la tool genérica que hacía esa consulta es justamente la que se sacó.

    Viaja con su FECHA porque este handler no conoce la zona del municipio:
    preguntar por "hoy" en UTC le erraría por un día cuatro horas de cada
    veinticuatro en Venezuela. Con la fecha al lado, el agente puede decir "al
    cambio del 1/9" y darse cuenta cuando la última cargada quedó vieja.
    """
    respx.get(f"{BASE}/api/data/alc_contribuyente").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/alc_liquidacion").mock(return_value=_liquidaciones())
    respx.get(f"{BASE}/api/data/alc_tasa_cambio").mock(return_value=_tasa())

    res = await _correr("mi_cuenta", {})
    assert res.data["tasa"] == {"fecha": "2026-09-01", "valor_bs": 322.75}


@respx.mock
async def test_sin_tasa_cargada_la_cuenta_igual_se_devuelve_con_tasa_en_none():
    """Degradar, no romper: los montos en unidades de cuenta siguen siendo
    ciertos, y el prompt ya sabe qué decir cuando no hay conversión."""
    respx.get(f"{BASE}/api/data/alc_contribuyente").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/alc_liquidacion").mock(return_value=_liquidaciones())
    respx.get(f"{BASE}/api/data/alc_tasa_cambio").mock(
        return_value=httpx.Response(200, json={"rows": [], "total": 0})
    )

    res = await _correr("mi_cuenta", {})
    assert res.data["identificado"] is True
    assert res.data["tasa"] is None


# --------------------------------------------------------------------------
# La escritura, atada a la misma identidad
# --------------------------------------------------------------------------


@respx.mock
async def test_informar_pago_rechaza_una_liquidacion_ajena():
    """Cerrar la lectura y dejar la escritura abierta sería mover el agujero:
    un id ajeno alcanzaría para ensuciarle el expediente a otro."""
    respx.get(f"{BASE}/api/data/alc_contribuyente").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/alc_liquidacion").mock(
        return_value=_liquidaciones([{"id": "l-mia", "data": {"estado": "pendiente"}}])
    )
    fn = respx.post(f"{BASE}/api/functions/alc_informar_pago").mock(
        return_value=httpx.Response(200, json={"value": {}})
    )

    res = await _correr(
        "informar_pago",
        {
            "liquidacion_id": "l-de-otro",
            "fecha": "2026-09-08",
            "monto_bs": 4034.38,
            "referencia": "PM-1",
            "medio": "pago_movil",
        },
    )

    assert res.data["registrado"] is False
    assert "no es de esta cuenta" in res.data["motivo"]
    # Y no llamó a la función: el rechazo es ANTES de escribir.
    assert fn.call_count == 0


@respx.mock
async def test_informar_pago_propia_llama_a_la_funcion_y_desenvuelve_value():
    respx.get(f"{BASE}/api/data/alc_contribuyente").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/alc_liquidacion").mock(
        return_value=_liquidaciones([{"id": "l-mia", "data": {"estado": "pendiente"}}])
    )
    fn = respx.post(f"{BASE}/api/functions/alc_informar_pago").mock(
        return_value=httpx.Response(
            200, json={"value": {"registrado": True, "pago_id": "p-1", "ya_estaba": False}}
        )
    )

    res = await _correr(
        "informar_pago",
        {
            "liquidacion_id": "l-mia",
            "fecha": "2026-09-08",
            "monto_bs": 4034.38,
            "referencia": "PM-1",
            "medio": "pago_movil",
        },
    )

    assert res.success
    # Desenvuelto: el prompt del agente nombra `registrado`, no `value.registrado`.
    assert res.data["registrado"] is True
    assert res.data["pago_id"] == "p-1"
    import json as _json

    enviado = _json.loads(fn.calls[0].request.content)
    assert enviado["args"]["liquidacion_id"] == "l-mia"
    # La tasa NO viaja: la resuelve la función de PRAXIS contra el día del pago.
    assert "tasa_aplicada" not in enviado["args"]


@respx.mock
async def test_informar_pago_sin_identidad_no_escribe():
    fn = respx.post(f"{BASE}/api/functions/alc_informar_pago").mock(
        return_value=httpx.Response(200, json={"value": {}})
    )
    res = await _correr(
        "informar_pago",
        {
            "liquidacion_id": "l-1",
            "fecha": "2026-09-08",
            "monto_bs": 1,
            "referencia": "PM-1",
            "medio": "pago_movil",
        },
        session_id="t_tenant-x__ag__prueba-abc-def",
    )
    assert res.data["identificado"] is False
    assert fn.call_count == 0


# --------------------------------------------------------------------------
# El clasificador: público a propósito
# --------------------------------------------------------------------------


@respx.mock
async def test_el_clasificador_se_consulta_sin_identidad():
    """Es la contracara de `mi_cuenta`: la alícuota de una actividad es
    información pública y se le contesta a cualquiera, esté o no en el padrón.
    Si esto exigiera identidad, un vecino que quiere saber cuánto va a pagar
    ANTES de inscribirse se quedaría sin respuesta."""
    ruta = respx.get(f"{BASE}/api/data/alc_actividad").mock(
        return_value=httpx.Response(200, json={"rows": [], "total": 0})
    )
    res = await _correr(
        "consultar_clasificador",
        {"filter": "codigo:eq:620100"},
        session_id="t_tenant-x__ag__prueba-x",
    )
    assert res.success
    assert ruta.calls[0].request.url.params["filter"] == "codigo:eq:620100"


# --------------------------------------------------------------------------
# Telegram: la identidad que no viene en el session_id
# --------------------------------------------------------------------------


@respx.mock
async def test_en_telegram_la_identidad_sale_del_sender_phone():
    """En Telegram el `session_id` NO trae teléfono: el usuario es un `chat.id`.

    El número lo pone Herald en `sender_phone` cuando la persona lo comparte
    con el botón `request_contact`, y Telegram garantiza que es el de su
    cuenta. Sin este camino, la vertical entera no puede identificar a nadie
    fuera de WhatsApp.
    """
    padron = respx.get(f"{BASE}/api/data/alc_contribuyente").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/alc_liquidacion").mock(return_value=_liquidaciones())
    respx.get(f"{BASE}/api/data/alc_tasa_cambio").mock(return_value=_tasa())

    res = await _correr(
        "mi_cuenta",
        {},
        session_id="t_tenant-x__ag__telegram__4242",
        ctx={"channel": "telegram", "sender": "4242", "sender_phone": TELEFONO},
    )

    assert res.data["identificado"] is True
    assert padron.calls[0].request.url.params["filter"] == f"telefono:eq:{TELEFONO}"


@respx.mock
async def test_en_telegram_sin_compartir_el_numero_no_identifica():
    """El caso normal antes de tocar el botón: `sender_phone` viene vacío."""
    padron = respx.get(f"{BASE}/api/data/alc_contribuyente").mock(return_value=_padron())
    res = await _correr(
        "mi_cuenta",
        {},
        session_id="t_tenant-x__ag__telegram__4242",
        ctx={"channel": "telegram", "sender": "4242", "sender_phone": ""},
    )
    assert res.data["identificado"] is False
    assert padron.call_count == 0


@respx.mock
async def test_el_sender_phone_gana_pero_sigue_sin_venir_de_los_argumentos():
    """La fuente nueva no reabre la vieja.

    `sender_phone` lo escribe Herald; un argumento lo escribe el MODELO. Si el
    handler mirara los argumentos —aunque fuera como último recurso— el
    agujero volvería por ahí.
    """
    padron = respx.get(f"{BASE}/api/data/alc_contribuyente").mock(return_value=_padron())
    res = await _correr(
        "mi_cuenta",
        {"sender_phone": "+584149999999", "telefono": "+584149999999"},
        session_id="t_tenant-x__ag__telegram__4242",
        ctx={"channel": "telegram", "sender": "4242", "sender_phone": ""},
    )
    assert res.data["identificado"] is False
    assert padron.call_count == 0


@respx.mock
async def test_sin_sender_phone_todavia_sirve_el_session_id_de_whatsapp():
    """El respaldo, para un Herald anterior al que manda `sender_phone`.

    Sin esto, desplegar este handler antes que ese Herald dejaría a la
    vertical sin identificar a nadie, ni siquiera en WhatsApp.
    """
    padron = respx.get(f"{BASE}/api/data/alc_contribuyente").mock(return_value=_padron())
    respx.get(f"{BASE}/api/data/alc_liquidacion").mock(return_value=_liquidaciones())
    respx.get(f"{BASE}/api/data/alc_tasa_cambio").mock(return_value=_tasa())

    res = await _correr("mi_cuenta", {}, ctx={"channel": "whatsapp"})
    assert res.data["identificado"] is True
    assert padron.calls[0].request.url.params["filter"] == f"telefono:eq:{TELEFONO}"
