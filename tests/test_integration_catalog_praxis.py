"""El manifest de PRAXIS: el ERP del cliente como integración declarativa.

Los tests de forma (nombres válidos, descripciones no vacías, placeholders
declarados) los hereda de `test_integration_conformance.py`, que está
parametrizado sobre todo el catálogo. Acá va lo que es propio de PRAXIS.
"""

import json

import httpx
import respx

from astromesh.integrations import IntegrationCatalog
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor

BASE = "https://erp.acme.tech"


def _praxis():
    catalog = IntegrationCatalog()
    catalog.discover()
    return catalog.get("praxis")


def _conn():
    return ResolvedConnection(name="praxis", material={"api_key": "praxis_K"}, base_url=BASE)


def test_the_manifest_brings_no_base_url_so_the_connection_must():
    """Un default acá le pegaría al ERP equivocado en silencio.

    `executor.py:84` resuelve `resolved.base_url or manifest.base_url`: si el
    manifest trajera uno, un tenant cuya conexión no lo declare terminaría
    escribiendo en el PRAXIS de otro. Sin default, falla y se nota.
    """
    assert _praxis().base_url is None


def test_it_exposes_exactly_the_three_actions():
    assert {a.name for a in _praxis().actions} == {
        "buscar_records",
        "crear_record",
        "actualizar_record",
    }


def test_auth_is_the_machine_api_key_as_a_bearer():
    manifest = _praxis()
    assert manifest.auth.scheme == "bearer"
    assert manifest.auth.credential == "api_key"


def test_the_two_writers_declare_writes_and_the_search_does_not():
    actions = {a.name: a for a in _praxis().actions}
    assert actions["buscar_records"].mutates is False
    assert actions["crear_record"].writes is True
    assert actions["actualizar_record"].writes is True


def test_the_mutating_actions_ask_the_agent_to_confirm_first():
    """La única confirmación que existe hoy, y es blanda.

    `writes: true` alimenta `ToolDefinition.requires_approval`
    (`astromesh/core/tools.py:168`) y NADIE lo lee. La contención dura es el
    rol acotado del bot en PRAXIS; esto es el pedido en el prompt, que el
    modelo puede saltear. Si alguien borra la frase de la descripción, no
    queda ni el pedido — por eso se fija acá.
    """
    actions = {a.name: a for a in _praxis().actions}
    for name in ("crear_record", "actualizar_record"):
        assert "confirm" in actions[name].description.lower(), name


def test_the_search_description_tells_the_model_where_the_fields_live():
    """Los campos de negocio vienen anidados bajo `data` (`mapRow`).

    Leer `rows[0].nombre` en vez de `rows[0].data.nombre` es exactamente el
    Critical de la rodaja anterior. El modelo sólo lee la descripción.
    """
    search = _praxis().action("buscar_records")
    assert "data" in search.description


@respx.mock
async def test_buscar_records_hits_api_data_with_the_bearer_key():
    route = respx.get(f"{BASE}/api/data/pedido").mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [{"id": "u-1", "data": {"estado": "pendiente"}}],
                "total": 1,
                "page": {"limit": 50, "offset": 0},
            },
        )
    )
    m = _praxis()
    result = await HttpActionExecutor().execute(
        m,
        m.action("buscar_records"),
        {"entidad": "pedido", "filter": "estado:eq:pendiente"},
        _conn(),
    )
    assert result.success is True
    # Sin `select`: el payload llega entero, `total` incluido — un agente que
    # tiene que contestar "cuántos pedidos hay" lo necesita.
    assert result.data["total"] == 1
    assert result.data["rows"][0]["data"]["estado"] == "pendiente"
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer praxis_K"
    assert request.url.params["filter"] == "estado:eq:pendiente"


@respx.mock
async def test_buscar_records_omits_the_optional_query_params_it_did_not_get():
    route = respx.get(f"{BASE}/api/data/cliente").mock(
        return_value=httpx.Response(200, json={"rows": [], "total": 0, "page": {}})
    )
    m = _praxis()
    await HttpActionExecutor().execute(
        m, m.action("buscar_records"), {"entidad": "cliente"}, _conn()
    )
    params = route.calls[0].request.url.params
    for optional in ("filter", "sort", "limit"):
        assert optional not in params, optional


@respx.mock
async def test_crear_record_sends_the_flat_field_map_as_the_whole_body():
    """PRAXIS espera el mapa plano, no `{"data": {...}}` (`records.controller.ts:64`)."""
    route = respx.post(f"{BASE}/api/data/cliente").mock(
        return_value=httpx.Response(201, json={"id": "u-9", "data": {"nombre": "Ana"}})
    )
    m = _praxis()
    result = await HttpActionExecutor().execute(
        m,
        m.action("crear_record"),
        {"entidad": "cliente", "campos": {"nombre": "Ana", "credito": 1200}},
        _conn(),
    )
    assert result.success is True
    assert json.loads(route.calls[0].request.content) == {"nombre": "Ana", "credito": 1200}


@respx.mock
async def test_actualizar_record_patches_the_row_by_id():
    route = respx.patch(f"{BASE}/api/data/pedido/8f1c0c4e-0000-4000-8000-000000000001").mock(
        return_value=httpx.Response(200, json={"id": "8f1c", "data": {"estado": "entregado"}})
    )
    m = _praxis()
    result = await HttpActionExecutor().execute(
        m,
        m.action("actualizar_record"),
        {
            "entidad": "pedido",
            "id": "8f1c0c4e-0000-4000-8000-000000000001",
            "campos": {"estado": "entregado"},
        },
        _conn(),
    )
    assert result.success is True
    assert json.loads(route.calls[0].request.content) == {"estado": "entregado"}


async def test_without_a_connection_base_url_it_fails_cleanly():
    """El precio de no traer default: un error legible, no un request al vacío."""
    m = _praxis()
    result = await HttpActionExecutor().execute(
        m,
        m.action("buscar_records"),
        {"entidad": "pedido"},
        ResolvedConnection(name="praxis", material={"api_key": "praxis_K"}),
    )
    assert result.success is False
    assert "base_url" in result.error


async def test_a_connection_without_the_api_key_fails_before_any_request():
    m = _praxis()
    result = await HttpActionExecutor().execute(
        m,
        m.action("buscar_records"),
        {"entidad": "pedido"},
        ResolvedConnection(name="praxis", material={}, base_url=BASE),
    )
    assert result.success is False
    assert "api_key" in result.error


async def test_an_entity_name_cannot_escape_the_path():
    """`entidad` la escribe el modelo y va pegada a la URL a mano."""
    m = _praxis()
    result = await HttpActionExecutor().execute(
        m, m.action("buscar_records"), {"entidad": "../../admin"}, _conn()
    )
    assert result.success is False
