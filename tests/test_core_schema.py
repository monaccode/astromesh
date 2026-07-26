import pytest

from astromesh.core.schema import InvalidToolParameters, normalize_tool_parameters


def test_none_passes_through():
    assert normalize_tool_parameters(None) is None


def test_shorthand_is_wrapped():
    result = normalize_tool_parameters({"city": {"type": "string", "description": "Ciudad"}})
    assert result == {
        "type": "object",
        "properties": {"city": {"type": "string", "description": "Ciudad"}},
    }


def test_real_json_schema_is_left_alone():
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "required": ["a"],
    }
    assert normalize_tool_parameters(schema) == schema


def test_bare_object_gets_empty_properties():
    assert normalize_tool_parameters({"type": "object"}) == {"type": "object", "properties": {}}


def test_normalization_is_idempotent():
    once = normalize_tool_parameters({"city": {"type": "string"}})
    assert normalize_tool_parameters(once) == once


def test_non_mapping_raises_with_type_name():
    with pytest.raises(InvalidToolParameters) as exc:
        normalize_tool_parameters(["a", "b"])
    assert exc.value.actual_type == "list"
