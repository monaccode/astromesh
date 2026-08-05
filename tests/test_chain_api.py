"""La ruta /run devuelve la answer de A más el bloque `chain`."""

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

BASE = """
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: {nombre}
spec:
  identity:
    description: "agente {nombre}"
  model:
    primary:
      provider: ollama
      model: "test"
      endpoint: "http://localhost:11434"
  prompts:
    system: "hola"
  orchestration:
    pattern: react
{extra}"""

CHAIN_A = """  output_schema:
    score: {type: integer}
  chain:
    on_complete:
      - agent: b
        when: "{{ output.data.score > 7 }}"
      - agent: c
"""


@pytest.fixture
def config_dir(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "a.agent.yaml").write_text(BASE.format(nombre="a", extra=CHAIN_A), encoding="utf-8")
    for nombre in ("b", "c", "solo"):
        (agents / f"{nombre}.agent.yaml").write_text(
            BASE.format(nombre=nombre, extra=""), encoding="utf-8"
        )
    return tmp_path


@pytest.fixture
async def client(config_dir, monkeypatch):
    monkeypatch.setenv("ASTROMESH_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("ASTROMESH_SKIP_RUNTIME", raising=False)
    from astromesh.api.main import app
    from astromesh.api.routes import agents as agents_route

    monkeypatch.setattr(agents_route, "_runtime", None)

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            c.app_state = app.state
            yield c


def _hacer_execute(respuesta):
    async def execute(query, context, model_fn, tool_fn, tools, max_iterations=10):
        return {"answer": respuesta, "steps": []}

    return execute


def _falsificar_agentes(client, respuestas):
    """Hace que cada agente devuelva la respuesta indicada, sin tocar providers."""
    runtime = client.app_state.workflow_engine._runtime
    for nombre, agente in runtime._agents.items():
        if nombre in respuestas:
            agente._pattern.execute = _hacer_execute(respuestas[nombre])


async def test_cadena_dispara_y_devuelve_links(client):
    _falsificar_agentes(
        client,
        {
            "a": 'Calificado.\n```json\n{"score": 9}\n```',
            "b": "mail enviado",
            "c": "registrado en crm",
        },
    )

    resp = await client.post("/v1/agents/a/run", json={"query": "un lead", "session_id": "s1"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"].startswith("Calificado."), "la answer debe ser la de A"
    assert body["data"] == {"score": 9}
    assert body["chain"]["status"] == "completed"

    por_agente = {link["agent"]: link for link in body["chain"]["links"]}
    assert por_agente["b"]["status"] == "success"
    assert por_agente["b"]["answer"] == "mail enviado"
    assert por_agente["c"]["status"] == "success"


async def test_condicion_falsa_deja_el_eslabon_skipped(client):
    _falsificar_agentes(
        client,
        {
            "a": 'Flojo.\n```json\n{"score": 2}\n```',
            "b": "mail enviado",
            "c": "registrado en crm",
        },
    )

    resp = await client.post("/v1/agents/a/run", json={"query": "un lead", "session_id": "s1"})

    body = resp.json()
    por_agente = {link["agent"]: link for link in body["chain"]["links"]}
    assert por_agente["b"]["status"] == "skipped"
    assert por_agente["b"]["reason"] == "condition_false"
    assert por_agente["c"]["status"] == "success", "un eslabón sin `when` dispara igual"


async def test_agente_sin_cadena_no_gana_el_bloque(client):
    """Guarda de regresión: la forma de hoy no cambia para quien no opta."""
    _falsificar_agentes(client, {"solo": "respuesta simple"})

    resp = await client.post("/v1/agents/solo/run", json={"query": "hola", "session_id": "s1"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "respuesta simple"
    assert body["chain"] is None
    assert body["data"] is None


async def test_grafo_de_la_cadena(client):
    resp = await client.get("/v1/agents/a/chain")

    assert resp.status_code == 200
    grafo = resp.json()
    assert grafo["agent"] == "a"
    assert grafo["mode"] == "sequential"
    assert [link["agent"] for link in grafo["links"]] == ["b", "c"]


async def test_grafo_404_si_no_hay_cadena(client):
    resp = await client.get("/v1/agents/solo/chain")
    assert resp.status_code == 404


async def test_grafo_404_si_no_existe_el_agente(client):
    resp = await client.get("/v1/agents/fantasma/chain")
    assert resp.status_code == 404
