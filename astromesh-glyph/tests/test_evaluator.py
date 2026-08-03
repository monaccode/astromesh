import pytest

from astromesh_glyph.capabilities import CapabilitySpec
from astromesh_glyph.runtime.evaluator import RETURNED, Evaluator
from astromesh_glyph.runtime.state import CallRecord, PartialState
from astromesh_glyph.runtime.values import Collection, unwrap, wrap
from astromesh_glyph.syntax.parser import parse


class FakeProvider:
    def __init__(self, responses=None, fail_on=None):
        self.responses = responses or {}
        self.fail_on = fail_on
        self.invocations = []

    def list_capabilities(self):
        return [CapabilitySpec(name=k, description="", parameters={}) for k in self.responses]

    async def invoke(self, name, args):
        self.invocations.append((name, args))
        if name == self.fail_on:
            raise RuntimeError("el proveedor remoto devolvió 503")
        return self.responses[name]


def _expr(source):
    return parse(f"x = {source}\n").body[0].value


async def _eval(source, env=None, provider=None):
    ev = Evaluator(provider or FakeProvider(), calls=[])
    return await ev.evaluate(_expr(source), env or {})


async def test_literals_and_names():
    assert await _eval("42") == 42
    assert await _eval("a", env={"a": "hola"}) == "hola"


async def test_attribute_access_on_a_record():
    assert await _eval("v.sku", env={"v": wrap({"sku": "A1"})}) == "A1"


async def test_capability_call_passes_evaluated_kwargs():
    provider = FakeProvider(responses={"search": [{"sku": "A"}]})
    result = await _eval('search(make="Toyota", year=2019)', provider=provider)
    assert provider.invocations == [("search", {"make": "Toyota", "year": 2019})]
    assert isinstance(result, Collection)


async def test_capability_results_are_wrapped():
    provider = FakeProvider(responses={"search": [{"sku": "A"}, {"sku": "B"}]})
    result = await _eval("search()", provider=provider)
    assert result.first.sku == "A"


async def test_pipe_applies_stages_left_to_right():
    provider = FakeProvider(
        responses={
            "search": [
                {"sku": "A", "kind": "oem", "rating": 5},
                {"sku": "B", "kind": "aftermarket", "rating": 9},
                {"sku": "C", "kind": "oem", "rating": 3},
            ]
        }
    )
    result = await _eval('search() | where(kind == "oem") | top(1, by=rating)', provider=provider)
    assert [r.sku for r in result.items] == ["A"]


async def test_binop_comparisons_and_boolean_operators():
    assert await _eval("a > 3", env={"a": 5}) is True
    assert await _eval("a > 3 and b", env={"a": 5, "b": False}) is False


async def test_dict_literal_with_shorthand():
    result = await _eval("{a, b}", env={"a": 1, "b": 2})
    assert unwrap(result) == {"a": 1, "b": 2}


async def test_calls_are_recorded_in_order():
    provider = FakeProvider(responses={"f": 1, "g": 2})
    calls = []
    ev = Evaluator(provider, calls=calls)
    await ev.evaluate(_expr("f()"), {})
    await ev.evaluate(_expr("g()"), {})
    assert [c.capability for c in calls] == ["f", "g"]
    assert all(c.ok for c in calls)


async def test_a_failing_capability_records_the_failure_and_propagates():
    provider = FakeProvider(responses={"f": 1}, fail_on="f")
    calls = []
    ev = Evaluator(provider, calls=calls)
    with pytest.raises(RuntimeError, match="503"):
        await ev.evaluate(_expr("f()"), {})
    assert calls[0].ok is False
    assert "503" in calls[0].error


async def test_if_executes_only_the_matching_branch():
    provider = FakeProvider(responses={"f": "sí", "g": "no"})
    ev = Evaluator(provider, calls=[])
    env = {"flag": True}
    stmt = parse("if flag:\n    a = f()\nelse:\n    b = g()\n").body[0]
    await ev.run_statement(stmt, env)
    assert env["a"] == "sí"
    assert "b" not in env
    assert [name for name, _ in provider.invocations] == ["f"]


async def test_return_signals_the_result():
    ev = Evaluator(FakeProvider(), calls=[])
    env = {"a": 1}
    kind, value = await ev.run_statement(parse("return a\n").body[0], env)
    assert kind is RETURNED
    assert value == 1


async def test_assignment_binds_into_the_environment():
    ev = Evaluator(FakeProvider(responses={"f": 7}), calls=[])
    env = {}
    await ev.run_statement(parse("a = 1\n").body[0], env)
    assert env["a"] == 1


def test_partial_state_prompt_lists_bindings_effects_and_error():
    state = PartialState(
        bindings={"v": [{"sku": "A"}]},
        executed=["n0"],
        failed_node="n1",
        error="restock: el proveedor remoto devolvió 503",
        calls=[CallRecord(capability="search", args={"make": "T"}, ok=True, result=[], error=None)],
    )
    text = state.to_prompt()
    assert "v" in text
    assert "search" in text
    assert "503" in text
    assert "no las repitas" in text
