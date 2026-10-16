"""Guardrails configuration normalization.

Only the shorthand is expanded here: rule semantics, defaults and validation live in core's
`astromesh.core.guardrails.GuardrailsEngine`, which the local runner builds from this config.
"""

from __future__ import annotations


def normalize_guardrails_config(guardrails: dict | None) -> dict:
    """Normalize guardrails config into the core `spec.guardrails` shape.

    Accepts:
        - None → {"input": [], "output": []}
        - {"input": ["pii_detection"]} → {"input": [{"type": "pii_detection"}]} (core default action)
        - {"input": [{"type": "pii_detection", "action": "warn"}]} → passthrough
    """
    if guardrails is None:
        return {"input": [], "output": []}
    return {
        side: [
            {"type": item} if isinstance(item, str) else item for item in guardrails.get(side) or []
        ]
        for side in ("input", "output")
    }
