"""`praxis_lca`: la integración que hace que un productor no pueda ver lo de otro.

La Carta es UN tenant con ~300 productores, y PRAXIS separa por tenant y no por
fila: la API key del bot alcanza a los 300. El aislamiento entre productores
vive acá, en estos handlers, y por eso los tests que más valen no son los de
forma sino los que prueban que **no hay forma de pedir lo de otro** — ni por
parámetro, ni dictando un teléfono, ni con un id ajeno.
"""

import httpx
import respx

from astromesh.integrations import IntegrationCatalog
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


# --- Forma -----------------------------------------------------------------


def test_ninguna_accion_recibe_la_identidad_como_parametro():
    """El invariante de la vertical: si un parámetro pudiera nombrar a un
    productor, el modelo podría nombrar a otro."""
    m = _lca()
    prohibidos = {"productor", "productor_id", "telefono", "sender", "sender_phone"}
    for accion in m.actions:
        assert not (set(accion.parameters) & prohibidos), f"{accion.name} nombra la identidad"


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
