import json

import httpx
import respx

from astromesh.integrations import IntegrationCatalog
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor

BASE = "https://clarus.example.com"


def _conocimiento():
    catalog = IntegrationCatalog()
    catalog.discover()
    manifest = catalog.get("conocimiento")
    # `discover` saltea con un log un manifest inválido o con slug distinto
    # del directorio: sin este assert el resto fallaría con un AttributeError
    # que no dice por qué.
    assert manifest is not None, "conocimiento no se descubrió: YAML inválido o slug != directorio"
    return manifest


def _conexion():
    return ResolvedConnection("conocimiento", {"api_key": "K"}, base_url=BASE)


def test_la_conexion_trae_el_base_url():
    assert _conocimiento().base_url is None


def test_las_acciones_no_escriben():
    manifest = _conocimiento()
    assert [a.name for a in manifest.actions] == ["buscar_en_documentos", "vencimientos"]
    for accion in manifest.actions:
        assert accion.writes is False
        assert accion.mutates is False


def test_la_descripcion_manda_los_numeros_al_catalogo():
    assert "catálogo" in _conocimiento().action("buscar_en_documentos").description


@respx.mock
async def test_busca_con_la_clave_en_el_header():
    route = respx.post(f"{BASE}/api/conocimiento/buscar").mock(
        return_value=httpx.Response(
            200,
            json={
                "disponible": True,
                "fragmentos": [{"documento": "Látex", "texto": "rinde 10 m2"}],
            },
        )
    )
    manifest = _conocimiento()
    result = await HttpActionExecutor().execute(
        manifest,
        manifest.action("buscar_en_documentos"),
        {"consulta": "cuánto rinde", "max": 3},
        _conexion(),
    )
    assert result.success is True
    assert result.data["disponible"] is True
    request = route.calls[0].request
    assert request.headers["X-Api-Key"] == "K"
    assert json.loads(request.content) == {"consulta": "cuánto rinde", "max": 3}


@respx.mock
async def test_sin_max_no_lo_manda():
    route = respx.post(f"{BASE}/api/conocimiento/buscar").mock(
        return_value=httpx.Response(200, json={"disponible": False, "fragmentos": []})
    )
    manifest = _conocimiento()
    await HttpActionExecutor().execute(
        manifest, manifest.action("buscar_en_documentos"), {"consulta": "garantía"}, _conexion()
    )
    assert json.loads(route.calls[0].request.content) == {"consulta": "garantía"}


CLARUS = "https://clarus.test"


@respx.mock
async def test_vencimientos_manda_cuit_y_rango_con_la_clave():
    route = respx.post(f"{CLARUS}/api/conocimiento/vencimientos").mock(
        return_value=httpx.Response(200, json={"vencimientos": [], "cubreHasta": "2026-12-31"})
    )
    manifest = _conocimiento()
    result = await HttpActionExecutor().execute(
        manifest,
        manifest.action("vencimientos"),
        {"cuit": "20123456786", "desde": "2026-10-01", "hasta": "2026-10-31"},
        ResolvedConnection("conocimiento", {"api_key": "k"}, base_url=CLARUS),
    )
    assert result.success is True
    request = route.calls[0].request
    assert request.headers["X-Api-Key"] == "k"
    assert request.content == b'{"cuit":"20123456786","desde":"2026-10-01","hasta":"2026-10-31"}'


@respx.mock
async def test_vencimientos_sin_fechas_no_las_manda():
    route = respx.post(f"{CLARUS}/api/conocimiento/vencimientos").mock(
        return_value=httpx.Response(200, json={"vencimientos": [], "cubreHasta": "2026-12-31"})
    )
    manifest = _conocimiento()
    await HttpActionExecutor().execute(
        manifest,
        manifest.action("vencimientos"),
        {"cuit": "20123456786"},
        ResolvedConnection("conocimiento", {"api_key": "k"}, base_url=CLARUS),
    )
    assert json.loads(route.calls[0].request.content) == {"cuit": "20123456786"}
