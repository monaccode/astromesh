"""Glyph — lenguaje de acción para agentes LLM."""

from astromesh_glyph.capabilities import CapabilityProvider, CapabilitySpec
from astromesh_glyph.errors import (
    GlyphCompileError,
    GlyphError,
    GlyphExecutionError,
    GlyphSyntaxError,
)

__version__ = "0.1.0"

__all__ = [
    "CapabilityProvider",
    "CapabilitySpec",
    "GlyphCompileError",
    "GlyphError",
    "GlyphExecutionError",
    "GlyphSyntaxError",
    "__version__",
]
