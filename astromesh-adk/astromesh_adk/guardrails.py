"""Guardrails configuration normalization."""

from __future__ import annotations

# Default actions per guardrail type
DEFAULT_ACTIONS = {
    "pii_detection": "redact",
    "topic_filter": "block",
    "max_length": "block",
    "cost_limit": "block",
    "content_filter": "redact",
}


def normalize_guardrails_config(guardrails: dict | None) -> dict:
    """Normalize guardrails config into Astromesh format.

    Accepts:
        - None → {"input": [], "output": []}
        - {"input": ["pii_detection"]} → {"input": [{"type": "pii_detection", "action": "redact"}]}
        - {"input": [{"type": "pii_detection", "action": "warn"}]} → passthrough
    """
    if guardrails is None:
        return {"input": [], "output": []}

    result = {}
    for side in ("input", "output"):
        items = guardrails.get(side, [])
        normalized = []
        for item in items:
            if isinstance(item, str):
                normalized.append({
                    "type": item,
                    "action": DEFAULT_ACTIONS.get(item, "block"),
                })
            elif isinstance(item, dict):
                normalized.append(item)
        result[side] = normalized

    return result
