"""Las tres tools sobre un ToolRegistry real: resultados, errores y argumentos sueltos."""

import json
from pathlib import Path

import pytest

from astromesh.core.tools import ToolRegistry
from astromesh.knowledge.okf import Bundle
from astromesh.knowledge.tools import TOOL_NAMES, register_bundle_tools

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "okf"


def _registry():
    registry = ToolRegistry()
    register_bundle_tools(registry, Bundle(FIX))
    return registry


def test_registers_the_three_tools():
    names = [s["function"]["name"] for s in _registry().get_tool_schemas()]
    assert sorted(names) == sorted(TOOL_NAMES)


async def test_kb_read_returns_the_concept_and_is_json_serializable():
    out = await _registry().execute("kb_read", {"concept_id": "metrics/revenue"})
    assert out["success"] is True
    assert out["data"]["title"] == "Revenue"
    json.dumps(out)


async def test_errors_come_back_as_results():
    out = await _registry().execute("kb_read", {"concept_id": "../outside"})
    assert out["success"] is False
    assert out["error"].startswith("outside bundle: ")


async def test_kb_index_defaults_to_root():
    out = await _registry().execute("kb_index", {})
    assert out["success"] is True
    assert out["data"].startswith("# Subdirectories")


async def test_kb_find_maps_type_and_tolerates_loose_arguments():
    out = await _registry().execute(
        "kb_find", {"type": "Metric", "tags": "finance", "limit": "2", "query": "ignored"}
    )
    assert out["success"] is True
    assert [r["id"] for r in out["data"]["results"]] == ["metrics/gross-margin", "metrics/revenue"]


async def test_kb_find_bad_limit_falls_back_to_default():
    out = await _registry().execute("kb_find", {"limit": "many"})
    assert out["success"] is True
    assert len(out["data"]["results"]) == 5


async def test_kb_find_coerces_non_string_arguments():
    out = await _registry().execute(
        "kb_find", {"text": 5, "type": 7, "tags": ["finance", 1], "limit": None}
    )
    assert out["success"] is True


def test_collision_with_an_existing_tool_raises():
    registry = ToolRegistry()

    async def _h(**_):
        return {}

    registry.register_internal(name="kb_read", handler=_h, description="x", parameters={})
    with pytest.raises(ValueError, match="kb_read"):
        register_bundle_tools(registry, Bundle(FIX))


async def test_kb_find_infinite_limit_does_not_fail():
    out = await _registry().execute("kb_find", {"limit": float("inf")})
    assert out["success"] is True


@pytest.mark.parametrize(("value", "expected"), [("false", False), ("true", True), (" Yes ", True)])
async def test_kb_find_include_deprecated_string(value, expected):
    out = await _registry().execute("kb_find", {"include_deprecated": value})
    ids = [r["id"] for r in out["data"]["results"]]
    assert ("metrics/gross-margin-legacy" in ids) is expected


async def test_yaml_alias_bomb_comes_back_as_an_error_not_a_crash(tmp_path):
    """Heredado de astromesh-okf 0.1: un alias de YAML ya no tumba la búsqueda ni el índice."""
    (tmp_path / "bomb.md").write_text("---\ntype: X\na: &a [*a]\n---\nbody\n")
    (tmp_path / "ok.md").write_text("---\ntype: X\n---\nbody\n")
    registry = ToolRegistry()
    register_bundle_tools(registry, Bundle(tmp_path))
    out = await registry.execute("kb_read", {"concept_id": "bomb"})
    assert out["success"] is False
    assert "aliases are not allowed" in out["error"]
    found = await registry.execute("kb_find", {})
    assert [r["id"] for r in found["data"]["results"]] == ["ok"]
    assert found["data"]["skipped_invalid"] == 1


async def test_errors_never_carry_absolute_paths(tmp_path):
    registry = ToolRegistry()
    register_bundle_tools(registry, Bundle(tmp_path))
    out = await registry.execute("kb_index", {"path": "a" * 5000})
    assert out["success"] is False
    assert out["error"].startswith("outside bundle")
    assert str(tmp_path) not in out["error"]
    assert len(out["error"]) < 300
