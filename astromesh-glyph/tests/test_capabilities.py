import pytest

from astromesh_glyph.capabilities import CapabilityProvider, CapabilitySpec
from astromesh_glyph.errors import GlyphError, GlyphSyntaxError


class _Stub:
    def list_capabilities(self):
        return [CapabilitySpec(name="search", description="busca", parameters={})]

    async def invoke(self, name, args):
        return {"name": name, "args": args}


def test_stub_satisfies_the_protocol_at_runtime():
    assert isinstance(_Stub(), CapabilityProvider)


def test_object_without_invoke_does_not_satisfy_the_protocol():
    class _Partial:
        def list_capabilities(self):
            return []

    assert not isinstance(_Partial(), CapabilityProvider)


def test_capability_spec_defaults_to_non_semantic():
    spec = CapabilitySpec(name="search", description="busca", parameters={})
    assert spec.is_semantic is False


def test_capability_spec_is_frozen():
    spec = CapabilitySpec(name="search", description="busca", parameters={})
    with pytest.raises(AttributeError):
        spec.name = "otro"


def test_syntax_error_carries_position_and_is_a_glyph_error():
    err = GlyphSyntaxError("token inesperado", line=3, column=7)
    assert isinstance(err, GlyphError)
    assert err.line == 3
    assert err.column == 7
    assert "línea 3" in str(err)
