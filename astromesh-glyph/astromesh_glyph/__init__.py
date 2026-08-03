"""Glyph — lenguaje de acción para agentes LLM."""

from astromesh_glyph.capabilities import CapabilityProvider, CapabilitySpec
from astromesh_glyph.errors import (
    GlyphCompileError,
    GlyphError,
    GlyphExecutionError,
    GlyphSyntaxError,
)
from astromesh_glyph.runtime.executor import execute
from astromesh_glyph.runtime.state import CallRecord, ExecutionResult, PartialState

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
    "__version__",
    "execute",
]
