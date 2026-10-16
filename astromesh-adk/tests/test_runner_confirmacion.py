"""Local confirmation gate (`requires_approval`) and `mode="propose"`, as core's engine."""

import pytest
from astromesh.integrations.propuestas import SOLO_PRINCIPAL

from astromesh_adk import agent, tool
from astromesh_adk.runner import ADKRuntime
from astromesh_adk.team import AgentTeam

from .test_runner_core070 import Provider


def _call(name, **arguments):
    return {"id": "1", "name": name, "arguments": arguments}


def _rt(provs: dict):
    return ADKRuntime(provider_factory=lambda p, m, c: provs[m])


def _pagar(ejecutadas):
    @tool(description="paga", requires_approval=True)
    async def pagar(monto: int) -> str:
        ejecutadas.append(monto)
        return "pagado"

    return pagar


def _agente(tools, name="a", model="claude-x"):
    @agent(name=name, model=model, tools=tools)
    async def a(ctx):
        """sys"""

    return a


async def test_requires_approval_no_ejecuta_la_primera_vez():
    ejecutadas = []
    prov = Provider("claude-x", [("", [_call("pagar", monto=10)]), ("¿confirmás?", [])])
    r = await _agente([_pagar(ejecutadas)]).run(
        "pagá 10", session_id="s", runtime=_rt({"claude-x": prov})
    )
    assert ejecutadas == [] and "Voy a ejecutar: pagar con monto: 10" in r.answer


async def test_confirmar_re_corriendo_con_si_ejecuta_una_vez():
    ejecutadas = []
    llamada = ("", [_call("pagar", monto=10)])
    prov = Provider("claude-x", [llamada, ("¿confirmás?", []), llamada, ("hecho", [])])
    rt, a = _rt({"claude-x": prov}), _agente([_pagar(ejecutadas)])
    await a.run("pagá 10", session_id="s", runtime=rt)
    r = await a.run("si", session_id="s", runtime=rt)
    assert ejecutadas == [10] and "Voy a ejecutar" not in r.answer


async def test_confirmar_con_otros_argumentos_no_ejecuta():
    ejecutadas = []
    prov = Provider(
        "claude-x",
        [
            ("", [_call("pagar", monto=10)]),
            ("¿confirmás?", []),
            ("", [_call("pagar", monto=99)]),
            ("no pude", []),
        ],
    )
    rt, a = _rt({"claude-x": prov}), _agente([_pagar(ejecutadas)])
    await a.run("pagá 10", session_id="s", runtime=rt)
    await a.run("si", session_id="s", runtime=rt)
    assert ejecutadas == []


def _supervisor(worker):
    sup = _agente([], name="sup", model="claude-sup")
    return AgentTeam(name="t", pattern="supervisor", supervisor=sup, workers=[worker])


async def test_un_miembro_de_equipo_no_autoconfirma():
    # Dentro de UNA corrida: el worker propone, y después el supervisor le delega "si".
    ejecutadas = []
    pagar10 = ("", [_call("pagar", monto=10)])
    provs = {
        "claude-sup": Provider(
            "claude-sup",
            [
                ("", [_call("worker", query="pagá 10")]),
                ("", [_call("worker", query="si")]),
                ("fin", []),
            ],
        ),
        "claude-w": Provider("claude-w", [pagar10, ("pido ok", []), pagar10, ("listo", [])]),
    }
    team = _supervisor(_agente([_pagar(ejecutadas)], name="worker", model="claude-w"))
    r = await team.run("pagá 10", session_id="s", runtime=_rt(provs))
    assert ejecutadas == []
    # El aviso lo pone la corrida que atiende a la persona: la del equipo.
    assert "Voy a ejecutar: pagar con monto: 10" in r.answer


async def test_un_equipo_confirma_con_si_de_la_persona():
    ejecutadas = []
    pagar10 = ("", [_call("pagar", monto=10)])
    provs = {
        "claude-sup": Provider(
            "claude-sup",
            [
                ("", [_call("worker", query="pagá 10")]),
                ("¿confirmás?", []),
                ("", [_call("worker", query="pagá 10")]),
                ("hecho", []),
            ],
        ),
        "claude-w": Provider("claude-w", [pagar10, ("pido ok", []), pagar10, ("pagado", [])]),
    }
    rt = _rt(provs)
    team = _supervisor(_agente([_pagar(ejecutadas)], name="worker", model="claude-w"))
    await team.run("pagá 10", session_id="s", runtime=rt)
    await team.run("si", session_id="s", runtime=rt)
    assert ejecutadas == [10]


def _crear(ejecutadas):
    @tool(description="crea", mode="propose")
    async def crear(nombre: str) -> str:
        ejecutadas.append(nombre)
        return "creado"

    return crear


async def test_mode_propose_no_ejecuta_y_devuelve_la_propuesta():
    ejecutadas = []
    prov = Provider("claude-x", [("", [_call("crear", nombre="x")]), ("propuesto", [])])
    r = await _agente([_crear(ejecutadas)]).run("creá x", runtime=_rt({"claude-x": prov}))
    assert ejecutadas == [] and r.propuestas[0]["tool"] == "crear"
    assert r.propuestas[0]["argumentos"] == {"nombre": "x"} and r.propuestas[0]["tipo"] == "adk"
    assert r.propuestas[0]["destino"] == "a" and r.propuestas[0]["operacion"] == "crear"


async def test_mode_propose_en_miembro_de_equipo_no_registra():
    ejecutadas = []
    provs = {
        "claude-sup": Provider(
            "claude-sup", [("", [_call("worker", query="creá x")]), ("fin", [])]
        ),
        "claude-w": Provider("claude-w", [("", [_call("crear", nombre="x")]), ("no", [])]),
    }
    team = _supervisor(_agente([_crear(ejecutadas)], name="worker", model="claude-w"))
    r = await team.run("creá x", runtime=_rt(provs))
    assert ejecutadas == [] and r.propuestas == []
    assert SOLO_PRINCIPAL in str(provs["claude-w"].calls[-1])


def test_mode_invalido_es_error():
    async def f(x: int) -> int:
        return x

    with pytest.raises(ValueError, match="mode"):
        tool("d", mode="dry")(f)
