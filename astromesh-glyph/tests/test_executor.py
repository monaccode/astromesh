import asyncio
import time

import pytest

from astromesh_glyph.capabilities import CapabilitySpec
from astromesh_glyph.errors import GlyphExecutionError
from astromesh_glyph.plan.compiler import compile_program
from astromesh_glyph.runtime.executor import execute
from astromesh_glyph.syntax.parser import parse

CAPS = [
    CapabilitySpec(name="slow", description="", parameters={}),
    CapabilitySpec(name="fast", description="", parameters={}),
    CapabilitySpec(name="boom", description="", parameters={}),
    CapabilitySpec(name="echo", description="", parameters={}),
]


class Provider:
    def __init__(self):
        self.order = []

    def list_capabilities(self):
        return CAPS

    async def invoke(self, name, args):
        self.order.append(name)
        if name == "slow":
            await asyncio.sleep(0.1)
            return [{"v": 1}]
        if name == "boom":
            raise RuntimeError("503 del proveedor")
        if name == "echo":
            return args
        return [{"v": 2}]


async def _run(source, provider=None, **kwargs):
    provider = provider or Provider()
    graph = compile_program(parse(source), CAPS)
    return await execute(graph, provider, **kwargs)


async def test_returns_the_value_of_the_return_statement():
    result = await _run("a = echo(x=1)\nreturn a\n")
    assert result.value == {"x": 1}


async def test_without_a_return_the_value_is_none():
    result = await _run("a = echo(x=1)\n")
    assert result.value is None


async def test_bindings_are_exposed_in_the_result():
    result = await _run("a = echo(x=1)\nb = echo(y=2)\n")
    assert set(result.bindings) == {"a", "b"}


async def test_independent_nodes_run_concurrently():
    started = time.monotonic()
    await _run("a = slow()\nb = slow()\nreturn {a, b}\n")
    elapsed = time.monotonic() - started
    # Dos sleeps de 0.1s secuenciales darían >= 0.2s.
    assert elapsed < 0.18


async def test_a_dependent_node_waits_for_its_dependency():
    provider = Provider()
    await _run("a = slow()\nb = a | top(1)\nc = fast()\nreturn {b, c}\n", provider=provider)
    assert "slow" in provider.order
    assert "fast" in provider.order


async def test_calls_are_collected_across_the_whole_run():
    result = await _run("a = echo(x=1)\nb = echo(y=2)\n")
    assert sorted(c.capability for c in result.calls) == ["echo", "echo"]


async def test_a_failure_raises_glyph_execution_error_with_partial_state():
    with pytest.raises(GlyphExecutionError) as exc:
        await _run("a = echo(x=1)\nb = boom()\nreturn {a, b}\n")
    err = exc.value
    assert err.capability == "boom"
    assert "a" in err.partial.bindings
    assert "503" in err.partial.error


async def test_the_partial_prompt_names_the_effects_already_applied():
    with pytest.raises(GlyphExecutionError) as exc:
        await _run("a = echo(x=1)\nb = a | top(1)\nc = boom()\n")
    text = exc.value.partial.to_prompt()
    assert "echo" in text
    assert "no las repitas" in text


async def test_node_timeout_is_reported_as_an_execution_error():
    with pytest.raises(GlyphExecutionError, match="tiempo"):
        await _run("a = slow()\n", node_timeout=0.01)


async def test_map_invokes_a_capability_once_per_item():
    """El patrón que los modelos escriben apenas hay una colección.

    `fast()` devuelve un elemento con campo `v`; el map lo proyecta llamando a
    `echo` con ese campo del elemento en scope.
    """
    provider = Provider()
    result = await _run(
        "w = fast()\ng = w | map({res: echo(marca=v)})\nreturn g\n", provider=provider
    )
    assert provider.order.count("echo") == 1
    assert result.value == [{"res": {"marca": 2}}]


async def test_map_calls_run_concurrently_up_to_the_fanout_cap():
    """Sin tope, un map sobre mil elementos tira abajo el servicio del otro lado."""
    activos = 0
    pico = 0

    class Contador:
        def list_capabilities(self):
            return CAPS

        async def invoke(self, name, args):
            nonlocal activos, pico
            if name == "muchos":
                return [{"n": i} for i in range(20)]
            activos += 1
            pico = max(pico, activos)
            await asyncio.sleep(0.02)
            activos -= 1
            return {"ok": args["n"]}

    caps = [*CAPS, CapabilitySpec(name="muchos", description="", parameters={})]
    graph = compile_program(parse("v = muchos()\ng = v | map({r: echo(n=n)})\nreturn g\n"), caps)

    await execute(graph, Contador(), max_fanout=4)
    assert pico <= 4

    activos = pico = 0
    await execute(graph, Contador(), max_fanout=16)
    assert pico > 4


async def test_an_if_branch_that_does_not_run_binds_its_names_to_null():
    """Sin esto, un nodo posterior que lea `b` espera para siempre."""
    result = await _run("a = echo(x=1)\nif a.x > 100:\n    b = echo(y=2)\nreturn {a, b}\n")
    assert result.value["b"] is None
    assert result.bindings["b"] is None
