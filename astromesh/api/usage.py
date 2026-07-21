"""Token usage derived from a run's trace.

Both POST /v1/agents/{name}/run and the WebSocket handler report usage, and both
derive it the same way: walk the trace's spans and sum what the providers
reported. It lives here so the two can't drift — the legacy metadata.usage
branch below is exactly the kind of detail that gets fixed in one copy and
forgotten in the other.
"""


def usage_from_trace(trace: dict | None) -> dict | None:
    """Sum token usage across a trace's spans.

    Returns {"tokens_in", "tokens_out", "model"}, or None when the trace reports
    no tokens at all (a run that never reached a provider, or a malformed trace).
    Never raises: a trace is data from the runtime, not a validated contract.
    """
    spans = trace.get("spans", []) if isinstance(trace, dict) else []
    if not isinstance(spans, list):
        return None

    total_in = 0
    total_out = 0
    model_used = ""

    for span in spans:
        attrs = span.get("attributes", {}) if isinstance(span, dict) else {}
        if not isinstance(attrs, dict):
            continue

        # The runtime stores tokens as input_tokens / output_tokens.
        total_in += attrs.get("input_tokens", 0)
        total_out += attrs.get("output_tokens", 0)

        # El runtime escribe el modelo como atributo directo del span llm.complete
        # (engine.py, llm_span.set_attribute("model", response.model)). Hasta v0.35.1
        # esto solo se leía de metadata.model —la rama heredada— así que con proveedores
        # nativos el campo volvía siempre vacío.
        if not model_used and isinstance(attrs.get("model"), str):
            model_used = attrs["model"]

        # Legacy / external providers nest them under metadata.usage.
        span_meta = attrs.get("metadata", {})
        if isinstance(span_meta, dict) and "usage" in span_meta:
            u = span_meta["usage"]
            total_in += u.get("prompt_tokens", 0)
            total_out += u.get("completion_tokens", 0)
        if isinstance(span_meta, dict) and "model" in span_meta and not model_used:
            model_used = span_meta["model"]

    if total_in or total_out:
        return {"tokens_in": total_in, "tokens_out": total_out, "model": model_used}
    return None
