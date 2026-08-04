"""Registro de `pattern: glyph` en el engine, sin romper el import sin extras."""

import os
import subprocess
import sys

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
