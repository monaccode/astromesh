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
SESION = f"whatsapp__{TELEFONO}"
CONTRIBUYENTE = "c-1"


def _alc():
    catalog = IntegrationCatalog()
    catalog.discover()
    return catalog.get("praxis_alcaldia")


def _conn():
    return ResolvedConnection(name="praxis", material={"api_key": "praxis_K"}, base_url=BASE)


async def _correr(accion: str, args: dict, session_id: str = SESION):
    m = _alc()
    return await HttpActionExecutor().execute(
        m, m.action(accion), args, _conn(), agent_name="tributos", session_id=session_id
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


def test_el_telefono_sale_del_session_id_de_herald():
    """Formato `<canal>__<usuario>`
    (`astromesh-herald/internal/domain/conversation.go:26-28`)."""
    assert telefono_de_sesion(SESION) == TELEFONO


def test_una_sesion_que_no_identifica_a_nadie_devuelve_none():
    casos = [
        "",  # sin sesión
        "prueba-mths8cm3-bullje-tributos",  # el banco de pruebas de Centuria
        "telegram__123456789",  # un id de chat NO es un teléfono del padrón
        "instagram__17841400000000000",  # un id de la plataforma tampoco
        "whatsapp__no-es-un-numero",
        "whatsapp__584141234567",  # sin el '+': no es como lo manda Herald
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

    res = await _correr("mi_cuenta", {}, session_id="prueba-mths8cm3-bullje-tributos")

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
    res = await _correr("mi_cuenta", {})
    assert res.data["solvente"] is True


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
        session_id="prueba-abc-def-tributos",
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
        "consultar_clasificador", {"filter": "codigo:eq:620100"}, session_id="prueba-x"
    )
    assert res.success
    assert ruta.calls[0].request.url.params["filter"] == "codigo:eq:620100"
