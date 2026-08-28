"""El manifest del vertical de cobranzas: las FUNCIONES de PRAXIS como tools.

Aparte del de `praxis` a propósito. Aquel es genérico —buscar, crear y
actualizar cualquier entidad— y sirve a todos los clientes de PRAXIS; meterle
acciones `cob_*` lo ataría a un vertical. Y un agente que negocia plata con una
persona necesita tools legibles: `simular_planes(obligacion, capacidad_pago)`
se entiende, un `invocar_funcion('cob_simular_planes', {...})` genérico no.

Los tests de forma (nombres válidos, placeholders declarados, un modo por
acción) los hereda de `test_integration_conformance.py`, parametrizado sobre
todo el catálogo. Acá va lo propio.
"""

import json

import httpx
import respx

from astromesh.integrations import IntegrationCatalog
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor

BASE = "https://erp.acme.tech"


def _cob():
    catalog = IntegrationCatalog()
    catalog.discover()
    return catalog.get("praxis_cobranzas")


def _conn():
    return ResolvedConnection(name="praxis", material={"api_key": "praxis_K"}, base_url=BASE)


def test_no_trae_base_url_propio():
    """Igual que `praxis`: un default le pegaría al ERP equivocado en silencio."""
    assert _cob().base_url is None


def test_expone_exactamente_las_dos_funciones():
    assert {a.name for a in _cob().actions} == {"simular_planes", "registrar_acuerdo"}


def test_comparte_la_credencial_de_maquina_con_praxis():
    """Las dos tools del agente usan la MISMA conexión (`praxis`) publicada en
    Nexus por el orquestador. Si el esquema o el nombre de la credencial no
    coincidieran, una de las dos quedaría sin material y fallaría recién en
    producción."""
    manifest = _cob()
    assert manifest.auth.scheme == "bearer"
    assert manifest.auth.credential == "api_key"


def test_solo_registrar_acuerdo_declara_writes():
    actions = {a.name: a for a in _cob().actions}
    assert actions["registrar_acuerdo"].writes is True
    assert not actions["simular_planes"].writes


@respx.mock
async def test_simular_planes_arma_el_body_que_praxis_espera():
    """`POST /api/functions/:name` toma `{ args: {...} }`
    (praxis/apps/backend/src/functions/functions.controller.ts:67)."""
    ruta = respx.post(f"{BASE}/api/functions/cob_simular_planes").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    m = _cob()
    await HttpActionExecutor().execute(
        m, m.action("simular_planes"), {"obligacion": "o-1", "capacidad_pago": 15000}, _conn()
    )
    enviado = json.loads(ruta.calls[0].request.content)
    assert enviado == {"args": {"obligacion": "o-1", "capacidad_pago": 15000}}


@respx.mock
async def test_un_opcional_ausente_no_viaja_como_null():
    """Un `capacidad_pago: null` NO es lo mismo que no mandarlo.

    Del otro lado, `numero(args.capacidad_pago)` lo trataría como una capacidad
    declarada de CERO y `planesLegales` devolvería cero planes — o sea "no
    puedo ofrecerte nada" cuando la persona no dijo nada.
    """
    ruta = respx.post(f"{BASE}/api/functions/cob_simular_planes").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    m = _cob()
    await HttpActionExecutor().execute(
        m, m.action("simular_planes"), {"obligacion": "o-1"}, _conn()
    )
    enviado = json.loads(ruta.calls[0].request.content)
    assert "capacidad_pago" not in enviado["args"]


@respx.mock
async def test_registrar_acuerdo_manda_las_obligaciones_como_lista():
    """`cob_registrar_acuerdo` exige una lista de strings y rechaza cualquier
    otra cosa; un string suelto sería un 422 que el agente no sabría leer."""
    ruta = respx.post(f"{BASE}/api/functions/cob_registrar_acuerdo").mock(
        return_value=httpx.Response(200, json={"value": "acuerdo-1"})
    )
    m = _cob()
    await HttpActionExecutor().execute(
        m,
        m.action("registrar_acuerdo"),
        {
            "obligaciones": ["o-1"],
            "pago_inicial": 50000,
            "cantidad_cuotas": 6,
            "descuento_pct": 0,
            "primera_cuota": "2026-09-15",
        },
        _conn(),
    )
    enviado = json.loads(ruta.calls[0].request.content)
    assert enviado["args"]["obligaciones"] == ["o-1"]
    assert enviado["args"]["cantidad_cuotas"] == 6


def test_las_descripciones_dicen_que_hacer_con_el_caso_raro():
    """Un LLM que recibe una lista vacía o un 422 sin contexto tiende a
    rendirse o a inventar. Las dos cosas son desastrosas acá: inventar un plan
    es ofrecerle a una persona algo que la agencia no puede cumplir."""
    actions = {a.name: a for a in _cob().actions}
    simular = actions["simular_planes"].description.lower()
    registrar = actions["registrar_acuerdo"].description.lower()

    assert "vac" in simular  # lista vacía = escalar, no bajar la cuota
    assert "escal" in simular
    assert "rechaz" in registrar  # el rechazo es parte del contrato
