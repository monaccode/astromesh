"""Glyph — lenguaje de acción para agentes LLM."""

from astromesh_glyph.capabilities import CapabilityProvider, CapabilitySpec
from astromesh_glyph.errors import (
    GlyphCompileError,
    GlyphError,
    GlyphExecutionError,
    GlyphSyntaxError,
)
from astromesh_glyph.plan.compiler import compile_program
from astromesh_glyph.plan.graph import PlanGraph, PlanNode
from astromesh_glyph.prompt.builder import build_system_block, extract_program
from astromesh_glyph.runtime.executor import execute
from astromesh_glyph.runtime.state import CallRecord, ExecutionResult, PartialState
from astromesh_glyph.syntax.parser import parse

__version__ = "0.1.0"

__all__ = [
    "CallRecord",
    "CapabilityProvider",
    "CapabilitySpec",
    "ExecutionResult",
    "GlyphCompileError",
    "GlyphError",
    "GlyphExecutionError",
    "GlyphSyntaxError",
    "PartialState",
    "PlanGraph",
    "PlanNode",
    "__version__",
    "build_system_block",
    "compile_program",
    "execute",
    "extract_program",
    "parse",
]
