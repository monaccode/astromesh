"""Registro de `pattern: glyph` en el engine, sin romper el import sin extras."""

import os
import pathlib
import subprocess
import sys

import pytest

from astromesh.orchestration.glyph_pattern import GlyphPattern
from astromesh.orchestration.patterns import ReActPattern
from astromesh.runtime.engine import AgentRuntime


def test_glyph_pattern_is_not_imported_at_engine_module_level():
    """El core tiene que importar sin el extra `glyph`.

    Se corre en un subproceso con `astromesh_glyph` bloqueado: si `engine.py` lo
    importara arriba, este import explota. Es la misma restricción que hace bootear
    la imagen de astromesh-os, y astromesh no la puede verificar de otra forma.
    """
    code = (
        "import sys\n"
        "sys.modules['astromesh_glyph'] = None\n"
        "import astromesh.runtime.engine\n"
        "import astromesh.api.main\n"
        "print('ok')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "ASTROMESH_SKIP_RUNTIME": "1"},
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


def test_the_engine_builds_a_glyph_pattern_from_the_yaml_spec():
    runtime = AgentRuntime.__new__(AgentRuntime)
    pattern = runtime._build_pattern({"orchestration": {"pattern": "glyph"}})
    assert isinstance(pattern, GlyphPattern)


def test_the_yaml_can_turn_off_narration():
    """Un agente encadenado consume output.data: la prosa es una llamada de más."""
    runtime = AgentRuntime.__new__(AgentRuntime)
    pattern = runtime._build_pattern(
        {"orchestration": {"pattern": "glyph", "narrate": False, "max_repairs": 1}}
    )
    assert pattern._narrate is False
    assert pattern._max_repairs == 1


def test_narration_is_on_by_default():
    runtime = AgentRuntime.__new__(AgentRuntime)
    pattern = runtime._build_pattern({"orchestration": {"pattern": "glyph"}})
    assert pattern._narrate is True
    assert pattern._max_repairs == 2


def test_an_unknown_pattern_still_falls_back_to_react():
    runtime = AgentRuntime.__new__(AgentRuntime)
    assert isinstance(runtime._build_pattern({"orchestration": {"pattern": "vaca"}}), ReActPattern)


def test_the_default_pattern_is_still_react():
    runtime = AgentRuntime.__new__(AgentRuntime)
    assert isinstance(runtime._build_pattern({}), ReActPattern)


def test_glyph_falls_back_to_react_when_the_extra_is_missing(monkeypatch):
    runtime = AgentRuntime.__new__(AgentRuntime)

    def _boom(name):
        raise ImportError("no module named astromesh_glyph")

    monkeypatch.setattr("astromesh.runtime.engine._import_glyph_pattern", _boom)
    pattern = runtime._build_pattern({"orchestration": {"pattern": "glyph"}})
    assert isinstance(pattern, ReActPattern)


def test_a_program_without_the_extra_is_an_error_not_a_fallback(monkeypatch):
    """Sin el extra, un agente con programa pasaba de 0 llamadas al modelo a un
    ReAct completo sin decir nada del programa ignorado. Contradice la decisión 2
    del spec: el costo de los dos modos difiere 400x."""
    from astromesh.errors import AgentConfigError

    runtime = AgentRuntime.__new__(AgentRuntime)

    def _boom(name):
        raise ImportError("no module named astromesh_glyph")

    monkeypatch.setattr("astromesh.runtime.engine._import_glyph_pattern", _boom)
    with pytest.raises(AgentConfigError, match="glyph"):
        runtime._build_pattern(
            {"orchestration": {"pattern": "glyph"}, "program": 'x = buscar(q="a")\n'},
            _TOOLS_YAML,
        )


async def test_the_caller_context_reaches_the_pattern():
    """Hoy no llega: agent.run pasa memory_context al patrón, no el del llamador.

    Sin esto un programa fijo no tiene de dónde sacar sus parámetros, y la
    regresión sería invisible porque ningún patrón existente lo usa.
    """
    from astromesh.orchestration.patterns import OrchestrationPattern

    visto = {}

    class Espia(OrchestrationPattern):
        async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
            visto["context"] = context
            return {"answer": "ok", "steps": []}

    runtime = AgentRuntime()
    await runtime.bootstrap()
    agent = next(iter(runtime._agents.values()))
    agent._pattern = Espia()

    await agent.run("hola", session_id="s1", context={"order_id": "A-77"})

    assert visto["context"]["_caller_context"] == {"order_id": "A-77"}


async def test_a_run_without_caller_context_still_gets_the_key():
    """Vacío, no ausente: así el patrón no tiene que distinguir dos casos."""
    from astromesh.orchestration.patterns import OrchestrationPattern

    visto = {}

    class Espia(OrchestrationPattern):
        async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
            visto["context"] = context
            return {"answer": "ok", "steps": []}

    runtime = AgentRuntime()
    await runtime.bootstrap()
    agent = next(iter(runtime._agents.values()))
    agent._pattern = Espia()

    await agent.run("hola", session_id="s2")

    assert visto["context"]["_caller_context"] == {}


async def test_the_reserved_keys_of_the_context_never_reach_the_pattern():
    """`_provider_override` lleva la API key del header `X-Astromesh-Provider-Key`.

    Si viajara dentro de `_caller_context`, un programa Glyph que hiciera
    `f(v=context)` la mandaría a `tool_args` y la traza la escribiría en disco —
    lo que el comentario de `tool_fn` declara prohibido— y un
    `ask("...", context=context)` la serializaría al proveedor del modelo.
    """
    from astromesh.orchestration.patterns import OrchestrationPattern

    visto = {}

    class Espia(OrchestrationPattern):
        async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
            visto["context"] = context
            return {"answer": "ok", "steps": []}

    runtime = AgentRuntime()
    await runtime.bootstrap()
    agent = next(iter(runtime._agents.values()))
    agent._pattern = Espia()

    await agent.run(
        "hola",
        session_id="s-secreta",
        context={
            "order_id": "A-77",
            "_secreta": "sk-no-debe-viajar",
            "_provider_override": {"name": "openai", "key": "sk-tampoco"},
        },
    )

    caller = visto["context"]["_caller_context"]
    assert caller == {"order_id": "A-77"}
    assert "sk-no-debe-viajar" not in str(caller)
    assert "sk-tampoco" not in str(caller)


async def test_the_memory_context_survives_the_new_key():
    """La clave nueva se agrega, no reemplaza: lo que trae el memory context sigue ahí.

    El plan asertaba `_history_messages`, pero MemoryManager.build_context nunca lo
    escribe: sólo lo leen ReActPattern y GlyphPattern, así que hoy es un camino
    muerto. Se verifica contra las claves que build_context sí produce.
    """
    from astromesh.orchestration.patterns import OrchestrationPattern

    visto = {}

    class Espia(OrchestrationPattern):
        async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
            visto["context"] = context
            return {"answer": "ok", "steps": []}

    runtime = AgentRuntime()
    await runtime.bootstrap()
    agent = next(iter(runtime._agents.values()))
    agent._pattern = Espia()

    await agent.run("hola", session_id="s3", context={"a": 1})

    assert {"conversation", "semantic", "episodic"} <= visto["context"].keys()
    assert visto["context"]["_caller_context"] == {"a": 1}


async def test_react_still_works_with_the_new_context_key():
    """La clave nueva la reciben TODOS los patrones; ninguno puede atragantarse."""
    from astromesh.orchestration.patterns import ReActPattern

    class Respuesta:
        content = "listo"
        tool_calls = None
        usage = {"input_tokens": 5, "output_tokens": 2}

    async def model_fn(messages, tools, role=None):
        return Respuesta()

    result = await ReActPattern().execute(
        query="q",
        context={"_history_messages": [], "_caller_context": {"a": 1}},
        model_fn=model_fn,
        tool_fn=None,
        tools=[],
    )
    assert result["answer"] == "listo"


_TOOLS_YAML = [
    {
        "type": "function",
        "function": {
            "name": "buscar",
            "description": "Busca algo",
            "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
        },
    }
]


def test_a_valid_program_reaches_the_pattern():
    runtime = AgentRuntime.__new__(AgentRuntime)
    pattern = runtime._build_pattern(
        {"orchestration": {"pattern": "glyph"}, "program": 'x = buscar(q="a")\nreturn x\n'},
        _TOOLS_YAML,
    )
    assert pattern._program == 'x = buscar(q="a")\nreturn x\n'


def test_a_program_that_does_not_compile_stops_the_agent_from_loading():
    """Un programa roto es un error de despliegue, no de la primera consulta."""
    from astromesh_glyph import GlyphCompileError

    runtime = AgentRuntime.__new__(AgentRuntime)
    with pytest.raises(GlyphCompileError, match="no existe"):
        runtime._build_pattern(
            {"orchestration": {"pattern": "glyph"}, "program": "x = inventada()\n"},
            _TOOLS_YAML,
        )


def test_a_program_with_a_syntax_error_stops_the_agent_from_loading():
    from astromesh_glyph import GlyphSyntaxError

    runtime = AgentRuntime.__new__(AgentRuntime)
    with pytest.raises(GlyphSyntaxError):
        runtime._build_pattern(
            {"orchestration": {"pattern": "glyph"}, "program": "x = = 1\n"}, _TOOLS_YAML
        )


def test_the_program_may_read_query_and_context():
    """Son predefinidas: un programa que las use tiene que compilar."""
    runtime = AgentRuntime.__new__(AgentRuntime)
    pattern = runtime._build_pattern(
        {"orchestration": {"pattern": "glyph"}, "program": "x = buscar(q=context.id)\nreturn x\n"},
        _TOOLS_YAML,
    )
    assert pattern._program is not None


def test_a_program_declared_with_another_pattern_stops_the_agent_from_loading():
    """Es un error de configuración: el programa no se ejecutaría nunca."""
    runtime = AgentRuntime.__new__(AgentRuntime)
    with pytest.raises(ValueError, match="pattern: glyph"):
        runtime._build_pattern(
            {"orchestration": {"pattern": "react"}, "program": "x = buscar(q=1)\n"}, _TOOLS_YAML
        )


def test_an_agent_without_a_program_still_builds():
    from astromesh.orchestration.glyph_pattern import GlyphPattern

    runtime = AgentRuntime.__new__(AgentRuntime)
    pattern = runtime._build_pattern({"orchestration": {"pattern": "glyph"}}, _TOOLS_YAML)
    assert isinstance(pattern, GlyphPattern)
    assert pattern._program is None


_EJEMPLO = pathlib.Path("config/agents/acuse-programa.agent.yaml")


def test_the_example_agent_declares_only_executable_tools():
    """Una tool `client` se anuncia pero no se ejecuta: devuelve `{"ok": True}`
    siempre (core/tools.py). Un programa fijo que lea sus campos falla en el 100%
    de las corridas, y este agente se despliega en toda instalación."""
    import yaml

    spec = yaml.safe_load(_EJEMPLO.read_text())["spec"]
    assert {t.get("type") for t in spec["tools"]} == {"builtin"}


async def test_the_example_agent_runs_end_to_end_without_the_model():
    """Que compile no alcanza: el ejemplo tiene que **correr**.

    Se ejecuta contra el `config/` real del repo —el mismo que se empaqueta en la
    rueda y en la imagen— con las tools builtin de verdad, y sin proveedor de
    modelo configurado: si el programa hiciera una sola llamada al modelo, esto
    fallaría.
    """
    import json

    runtime = AgentRuntime()
    await runtime.bootstrap()

    assert runtime._agent_status.get("acuse-programa") == "deployed", runtime.agent_error(
        "acuse-programa"
    )

    result = await runtime.run(
        "acuse-programa",
        "recibí la solicitud",
        session_id="s-ejemplo",
        context={"zona": "America/Argentina/Buenos_Aires"},
    )

    datos = json.loads(result["answer"])
    assert datos["acuse"]["data"]["zona"] == "America/Argentina/Buenos_Aires"
    assert datos["acuse"]["data"]["hora_utc"].endswith("+00:00")
    # Las tres llamadas del programa corrieron de verdad, ninguna quedó en `{"ok": True}`.
    acciones = [s.action for s in result["steps"] if getattr(s, "action", None)]
    assert acciones == ["datetime_now", "datetime_now", "json_transform"]


async def test_a_broken_program_leaves_its_reason_in_the_agent_status(tmp_path, monkeypatch):
    """En el bootstrap el error se logueaba y nada más: el primer run daba un
    404 "Agent not found" que no menciona la compilación. El motivo tiene que
    poder leerse desde el estado del agente."""
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "roto.agent.yaml").write_text(
        "apiVersion: astromesh/v1\n"
        "kind: Agent\n"
        "metadata:\n"
        "  name: roto\n"
        "spec:\n"
        "  orchestration:\n"
        "    pattern: glyph\n"
        "  program: |\n"
        "    x = inventada()\n",
        encoding="utf-8",
    )

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    assert runtime._agent_status["roto"] == "draft"
    motivo = runtime.agent_error("roto")
    assert motivo is not None
    assert "no existe" in motivo
    entrada = next(a for a in runtime.list_agents() if a["name"] == "roto")
    assert "no existe" in entrada["error"]


def test_a_healthy_agent_carries_no_error_in_its_listing():
    """El campo sólo aparece cuando hay algo que contar."""
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime._agents = {}
    runtime._agent_status = {"sano": "draft"}
    runtime._agent_errors = {}
    runtime._agent_configs = {"sano": {"metadata": {"name": "sano"}}}
    assert "error" not in runtime.list_agents()[0]
