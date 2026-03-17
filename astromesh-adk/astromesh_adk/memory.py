"""Memory configuration normalization."""

from __future__ import annotations

CONVERSATIONAL_DEFAULTS = {
    "strategy": "sliding_window",
    "max_turns": 50,
}

SEMANTIC_DEFAULTS = {
    "similarity_threshold": 0.7,
    "max_results": 5,
}


def normalize_memory_config(memory: str | dict | None) -> dict:
    """Normalize memory config from shorthand or full dict.

    Accepts:
        - None → {}
        - "sqlite" → {"conversational": {"backend": "sqlite", ...defaults}}
        - {"conversational": "redis"} → {"conversational": {"backend": "redis", ...defaults}}
        - {"conversational": {"backend": "sqlite", "strategy": "summary"}} → passthrough with defaults
    """
    if memory is None:
        return {}

    if isinstance(memory, str):
        return {
            "conversational": {"backend": memory, **CONVERSATIONAL_DEFAULTS},
        }

    result = {}
    for mem_type, value in memory.items():
        if isinstance(value, str):
            defaults = CONVERSATIONAL_DEFAULTS if mem_type == "conversational" else SEMANTIC_DEFAULTS
            result[mem_type] = {"backend": value, **defaults}
        elif isinstance(value, dict):
            defaults = CONVERSATIONAL_DEFAULTS if mem_type == "conversational" else SEMANTIC_DEFAULTS
            merged = {**defaults, **value}
            result[mem_type] = merged
        else:
            result[mem_type] = value

    return result
