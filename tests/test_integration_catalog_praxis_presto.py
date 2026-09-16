"""El manifest del vertical PRESTO: `prs_crear_presupuesto` de PRAXIS como tool.

Existe por latencia medida en mvp el 2026-09-16: el vendedor armaba el
presupuesto con tres escrituras genéricas de `praxis` (presupuesto, una línea
por producto, paso a confirmado) y cada una costaba un viaje al LLM. La función
lo hace en una transacción
(praxis/apps/backend/src/packages/presto/presto.functions.ts, CREAR_PRESUPUESTO).

Los tests de forma los hereda de `test_integration_conformance.py`. Acá va lo
propio: que las líneas viajen como LISTA de objetos y que el modelo vea su
esquema.
"""

import json

import httpx
import respx

from astromesh.integrations import IntegrationCatalog
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor

BASE = "https://erp.acme.tech"


def _presto():
    catalog = IntegrationCatalog()
    catalog.discover()
    return catalog.get("praxis_presto")


def _conn():
    return ResolvedConnection(name="praxis", material={"api_key": "praxis_K"}, base_url=BASE)


def test_no_trae_base_url_propio_y_comparte_la_credencial_de_praxis():
    m = _presto()
    assert m.base_url is None
    assert m.auth.scheme == "bearer"
    assert m.auth.credential == "api_key"


def test_expone_crear_presupuesto_y_escribe():
    m = _presto()
    assert {a.name for a in m.actions} == {"crear_presupuesto"}
    assert m.action("crear_presupuesto").writes is True


def test_el_modelo_ve_el_esquema_de_cada_linea():
    """Sin `items`, el modelo no sabe que cada línea es {producto, cantidad} y
    arma lo que se le ocurre; PRAXIS lo rechaza con un 422."""
    schema = _presto().action("crear_presupuesto").tool_parameters()
    lineas = schema["properties"]["lineas"]
    assert lineas["type"] == "array"
    assert lineas["items"]["type"] == "object"
    assert set(lineas["items"]["properties"]) == {"producto", "cantidad", "pedido_textual"}
    assert lineas["items"]["required"] == ["producto", "cantidad"]
    assert set(schema["required"]) == {"canal", "direccion", "lineas"}


@respx.mock
async def test_las_lineas_viajan_como_lista_de_objetos_y_los_opcionales_no_viajan():
    """`{lineas}` solo en el string conserva el tipo (interpolation.py,
    `interpolate_structure`): un string con el JSON adentro sería un 422."""
    ruta = respx.post(f"{BASE}/api/functions/prs_crear_presupuesto").mock(
        return_value=httpx.Response(200, json={"value": {"creado": True}})
    )
    m = _presto()
    lineas = [
        {"producto": "p-1", "cantidad": 5, "pedido_textual": "5 cementos"},
        {"producto": "p-2", "cantidad": 1},
    ]
    await HttpActionExecutor().execute(
        m,
        m.action("crear_presupuesto"),
        {"canal": "webchat", "direccion": "webchat-abc", "lineas": lineas},
        _conn(),
    )
    enviado = json.loads(ruta.calls[0].request.content)
    assert enviado == {"args": {"canal": "webchat", "direccion": "webchat-abc", "lineas": lineas}}


def test_la_descripcion_dice_que_hacer_si_no_se_creo():
    """Un `creado: false` leído como éxito es un "listo, te llega el PDF" sobre
    un presupuesto que no existe."""
    d = _presto().action("crear_presupuesto").description.lower()
    assert "no se escribió nada" in d
    assert "motivo" in d
