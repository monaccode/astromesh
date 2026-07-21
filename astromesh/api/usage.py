"""Token usage derived from a run's trace.

Both POST /v1/agents/{name}/run and the WebSocket handler report usage, and both
derive it the same way: walk the trace's spans and sum what the providers
reported. It lives here so the two can't drift — the legacy metadata.usage
branch below is exactly the kind of detail that gets fixed in one copy and
forgotten in the other.

A single run routinely touches more than one model: orchestration patterns that
consult several (supervisor, pipeline, swarm, parallel_fan_out), per-role model
routing, and provider fallback. The flat `model` field cannot represent that, so
`by_model` carries the breakdown — grouped by (provider, model, role), which is
what a cost attribution needs.
"""


def _as_float(value) -> float:
    """A trace is data from the runtime, not a validated contract: never raise."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def _as_int(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def usage_from_trace(trace: dict | None) -> dict | None:
    """Sum token usage across a trace's spans.

    Returns {"tokens_in", "tokens_out", "model", "by_model"}, or None when the
    trace reports no tokens at all (a run that never reached a provider, or a
    malformed trace). Never raises.

    `model` is the first model seen, kept for backward compatibility; it has no
    correct value on a multi-model run. `by_model` is the authoritative
    breakdown: one entry per (provider, model, role), ordered by total tokens
    descending, then by model name.
    """
    spans = trace.get("spans", []) if isinstance(trace, dict) else []
    if not isinstance(spans, list):
        return None

    total_in = 0
    total_out = 0
    model_used = ""
    breakdown: dict[tuple[str, str, str], dict] = {}

    for span in spans:
        attrs = span.get("attributes", {}) if isinstance(span, dict) else {}
        if not isinstance(attrs, dict):
            continue

        # The runtime stores tokens as input_tokens / output_tokens.
        span_in = _as_int(attrs.get("input_tokens", 0))
        span_out = _as_int(attrs.get("output_tokens", 0))
        total_in += span_in
        total_out += span_out

        # El runtime escribe el modelo como atributo directo del span llm.complete
        # (engine.py, llm_span.set_attribute("model", response.model)). Hasta v0.35.1
        # esto solo se leía de metadata.model —la rama heredada— así que con proveedores
        # nativos el campo volvía siempre vacío.
        model = attrs.get("model")
        if isinstance(model, str) and model:
            if not model_used:
                model_used = model
            provider = attrs.get("provider")
            provider = provider if isinstance(provider, str) else ""
            role = attrs.get("resolved_role") or attrs.get("role") or "default"
            role = role if isinstance(role, str) else "default"

            key = (provider, model, role)
            entry = breakdown.get(key)
            if entry is None:
                entry = {
                    "provider": provider,
                    "model": model,
                    "role": role,
                    "calls": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "cost": 0.0,
                }
                breakdown[key] = entry
            entry["calls"] += 1
            entry["tokens_in"] += span_in
            entry["tokens_out"] += span_out
            entry["cost"] += _as_float(attrs.get("cost"))

        # Legacy / external providers nest them under metadata.usage.
        span_meta = attrs.get("metadata", {})
        if isinstance(span_meta, dict) and "usage" in span_meta:
            u = span_meta["usage"]
            total_in += u.get("prompt_tokens", 0)
            total_out += u.get("completion_tokens", 0)
        if isinstance(span_meta, dict) and "model" in span_meta and not model_used:
            model_used = span_meta["model"]

    if total_in or total_out:
        by_model = sorted(
            breakdown.values(),
            key=lambda e: (-(e["tokens_in"] + e["tokens_out"]), e["model"]),
        )
        return {
            "tokens_in": total_in,
            "tokens_out": total_out,
            "model": model_used,
            "by_model": by_model,
        }
    return None
