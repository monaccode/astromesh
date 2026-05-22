"""Tests for @tool decorator's Pydantic model parameter support."""
from __future__ import annotations

import asyncio

from pydantic import BaseModel

from astromesh_adk import tool


class _Input(BaseModel):
    a: int
    b: str = "default"


class _Output(BaseModel):
    sum_a_doubled: int
    b_upper: str


@tool(description="test pydantic input")
async def _example(input: _Input) -> _Output:
    return _Output(sum_a_doubled=input.a * 2, b_upper=input.b.upper())


def test_pydantic_param_schema_uses_model_schema():
    """The auto-generated schema for a single Pydantic-typed param is the model's own schema."""
    schema = _example.parameters_schema
    assert schema["type"] == "object"
    assert "a" in schema["properties"]
    assert "b" in schema["properties"]
    assert schema["properties"]["a"]["type"] == "integer"
    # `a` is required; `b` has a default
    assert "a" in schema.get("required", [])
    assert "b" not in schema.get("required", [])


def test_pydantic_param_call_with_field_kwargs():
    """Calling with the model's field kwargs constructs the model and passes it through."""
    result = asyncio.run(_example(a=5, b="hello"))
    assert isinstance(result, _Output)
    assert result.sum_a_doubled == 10
    assert result.b_upper == "HELLO"


def test_pydantic_param_call_with_nested_dict():
    """Alternate calling form — the param name as key, value as a dict."""
    result = asyncio.run(_example(input={"a": 3, "b": "x"}))
    assert result.sum_a_doubled == 6
    assert result.b_upper == "X"


def test_non_pydantic_params_unchanged():
    """Tools without Pydantic params keep their existing schema/call behavior."""

    @tool(description="primitive")
    async def add(a: int, b: int) -> int:
        return a + b

    assert add.parameters_schema["properties"]["a"]["type"] == "integer"
    assert add.parameters_schema["properties"]["b"]["type"] == "integer"
    assert asyncio.run(add(a=2, b=3)) == 5
