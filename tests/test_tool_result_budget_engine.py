"""El tope de tokens del resultado de una tool, del YAML al mensaje del modelo."""

import logging

import pytest
import yaml

from astromesh.core import tokens
from astromesh.core.tokens import estimate_tokens
from astromesh.orchestration.glyph_pattern import GlyphPattern
from astromesh.providers.base import CompletionResponse
from astromesh.runtime.engine import AgentRuntime, claves_ignoradas
from astromesh.tools import ToolLoader
from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


GRANDE = [{"id": i, "v": "x" * 40} for i in range(2000)]


class _Grande(BuiltinTool):
    name = "grande"
    description = "devuelve un resultado enorme"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True, data=GRANDE, metadata={})


@pytest.fixture(autouse=True)
def tool_grande(monkeypatch):
    # El catálogo builtin real no tiene una tool que devuelva algo enorme sin red.
    monkeypatch.setattr(ToolLoader, "auto_discover", lambda self: self.register_class(_Grande))


def _manifest(tools=None, orchestration=None):
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "tb-agent", "version": "0.1.0"},
        "spec": {
            "identity": {"description": "demo"},
            "model": {"primary": {"provider": "ollama", "model": "llama3"}},
            "prompts": {"system": "sos un agente"},
            "orchestration": {"pattern": "react", **(orchestration or {})},
            "tools": [{"name": "grande", "type": "builtin"}] if tools is None else tools,
        },
    }


async def _agente(tmp_path, manifest):
    d = tmp_path / "config"
    (d / "agents").mkdir(parents=True, exist_ok=True)
    (d / "agents" / "tb-agent.agent.yaml").write_text(yaml.safe_dump(manifest))
    rt = AgentRuntime(config_dir=str(d))
    await rt.bootstrap()
    assert "tb-agent" in rt._agents, rt._agent_errors
    return rt._agents["tb-agent"]


def _guion(agente, tool_name="grande"):
    vistos = []

    async def route(messages, requirements=None, **kw):
        vistos.append(list(messages))
        if len(vistos) == 1:
            return CompletionResponse(
                content="",
                model="m",
                provider="p",
                usage={},
                latency_ms=1.0,
                cost=0.0,
                tool_calls=[{"id": "t1", "name": tool_name, "arguments": {}}],
            )
        return CompletionResponse(
            content="ok", model="m", provider="p", usage={}, latency_ms=1.0, cost=0.0
        )

    agente._routers["default"].route = route
    return vistos


def _tokens_del_tool(vistos):
    msgs = [m for m in vistos[-1] if m.get("role") == "tool"]
    assert msgs
    return msgs[-1]["content"]


async def test_max_result_tokens_de_la_tool(tmp_path):
    ag = await _agente(
        tmp_path, _manifest([{"name": "grande", "type": "builtin", "max_result_tokens": 150}])
    )
    vistos = _guion(ag)
    await ag.run("hola", session_id="s")
    assert estimate_tokens(_tokens_del_tool(vistos)) <= 150


async def test_max_tool_result_tokens_del_agente(tmp_path):
    ag = await _agente(tmp_path, _manifest(orchestration={"max_tool_result_tokens": 300}))
    vistos = _guion(ag)
    await ag.run("hola", session_id="s")
    assert estimate_tokens(_tokens_del_tool(vistos)) <= 300


async def test_sin_nada_rige_el_default(tmp_path):
    ag = await _agente(tmp_path, _manifest())
    vistos = _guion(ag)
    await ag.run("hola", session_id="s")
    contenido = _tokens_del_tool(vistos)
    assert estimate_tokens(contenido) <= 8000
    assert "_omitidos" in contenido


@pytest.mark.parametrize("malo", [0, -5, "mucho", True])
async def test_valor_invalido_avisa_y_usa_el_default(tmp_path, caplog, malo):
    m = _manifest(
        [{"name": "grande", "type": "builtin", "max_result_tokens": malo}],
        {"max_tool_result_tokens": malo},
    )
    with caplog.at_level(logging.WARNING):
        ag = await _agente(tmp_path, m)
    avisos = [r.getMessage() for r in caplog.records if "tb-agent" in r.getMessage()]
    assert any("grande" in a and repr(malo) in a for a in avisos)
    assert any("max_tool_result_tokens" in a and repr(malo) in a for a in avisos)
    assert ag._presupuesto_tools["default"] == 8000
    assert ag._presupuesto_tools["por_tool"] == {}


@pytest.mark.parametrize("tipo", ["builtin", "agent", "client", "integration", "api", "mcp"])
def test_max_result_tokens_no_es_clave_ignorada(tipo):
    assert claves_ignoradas({"type": tipo, "name": "x", "max_result_tokens": 10}) == []


MANIFEST_INTEGRACION = """
apiVersion: astromesh/v1
kind: Integration
metadata: {name: demo, version: 0.1.0, description: demo}
spec:
  base_url: "https://api.demo.test"
  auth: {scheme: bearer, credential: access_token}
  actions:
    - name: uno
      description: "Uno"
      request: {method: GET, path: "/uno"}
    - name: dos
      description: "Dos"
      request: {method: GET, path: "/dos"}
"""


async def test_el_tope_aplica_a_cada_accion_de_una_integracion(tmp_path, monkeypatch):
    import astromesh.runtime.engine as engine_module
    from astromesh.integrations import IntegrationCatalog

    root = tmp_path / "catalog"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "integration.yaml").write_text(MANIFEST_INTEGRACION)
    catalog = IntegrationCatalog()
    catalog.discover(root)
    monkeypatch.setattr(engine_module, "default_catalog", lambda: catalog)
    ag = await _agente(
        tmp_path,
        _manifest(
            [
                {
                    "type": "integration",
                    "name": "demo",
                    "connection": "c",
                    "actions": ["uno", "dos"],
                    "max_result_tokens": 120,
                }
            ]
        ),
    )
    assert ag._presupuesto_tools["por_tool"] == {"demo_uno": 120, "demo_dos": 120}


async def test_la_traza_lleva_tokens_y_recorte(tmp_path):
    ag = await _agente(tmp_path, _manifest())
    _guion(ag)
    result = await ag.run("hola", session_id="s")
    spans = result["trace"]["spans"]
    call = next(s for s in spans if s["name"] == "tool.call")
    assert call["attributes"]["tool.result_tokens"] > 8000
    orq = next(s for s in spans if s["name"] == "orchestration")
    pasos = [e["attributes"] for e in orq["events"] if e["name"] == "orch_step"]
    assert any(p.get("truncated") is True and p.get("omitted", 0) > 0 for p in pasos)


async def test_glyph_recibe_los_datos_completos():
    async def tool_fn(name, args):
        return GRANDE

    async def explota(messages, tools, role=None):
        raise AssertionError("no debe llamar al modelo")

    tools = [
        {
            "type": "function",
            "function": {
                "name": "buscar",
                "description": "d",
                "parameters": {
                    "type": "object",
                    "properties": {"q": {"type": "string"}},
                    "required": ["q"],
                },
            },
        }
    ]
    result = await GlyphPattern(program='v = buscar(q="a")\nreturn v\n', narrate=False).execute(
        query="x",
        context={
            "_caller_context": {},
            "_presupuesto_tools": {"default": 50, "por_tool": {}},
        },
        model_fn=explota,
        tool_fn=tool_fn,
        tools=tools,
        max_iterations=6,
    )
    assert "1999" in result["answer"]
    assert result["answer"].count('"id"') == 2000


@pytest.mark.parametrize("modulo", ["test_mcp_tool", "test_api_tool"])
async def test_max_result_tokens_en_api_y_mcp_carga_y_aplica(tmp_path, modulo):
    import copy
    import importlib

    from astromesh.integrations.api import manifiesto_de_api
    from astromesh.integrations.mcp import nombre_de_tool

    m = importlib.import_module(f"tests.{modulo}")
    ficha = copy.deepcopy(m.SERVIDOR if modulo == "test_mcp_tool" else m.API)
    ficha["max_result_tokens"] = 77
    if ficha["type"] == "mcp":
        esperados = {nombre_de_tool(ficha["name"], t["name"]) for t in ficha["tools"]}
    else:
        manifest, _ = manifiesto_de_api(ficha)
        esperados = {f"{manifest.slug}_{a.name}" for a in manifest.actions}
    ag = await _agente(tmp_path, _manifest([ficha]))
    assert ag._presupuesto_tools["por_tool"] == dict.fromkeys(esperados, 77)
