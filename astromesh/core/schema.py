"""Normalización de esquemas de parámetros de tools.

Compartido por el loader de agentes (runtime) y por el marco de
integraciones (infrastructure): ambos aceptan la misma taquigrafía YAML.
"""


class InvalidToolParameters(Exception):
    """Raised by normalize_tool_parameters when `parameters` is present but not
    a mapping (e.g. a YAML list, string, int or bool). Carries the offending
    type's name so the caller can name it in a warning."""

    def __init__(self, actual_type: str):
        self.actual_type = actual_type
        super().__init__(actual_type)


def normalize_tool_parameters(parameters: dict | None) -> dict | None:
    """Turn a YAML-authored 'parameters' block into valid JSON Schema.

    Every shipped agent YAML writes tool parameters in a shorthand — a flat
    mapping of param name -> {type, description}, e.g.:

        parameters:
          company_name:
            type: string
            description: "Company name to look up"

    That is not JSON Schema: it has no `type: object` and no `properties`
    wrapper. Passed through untouched, it reaches the model exactly as
    written, and a provider that validates function-calling schemas
    (Anthropic's input_schema requires `type: object`; OpenAI strict mode
    rejects the shape outright) 400s the whole request — not just that one
    tool. This wraps the shorthand into `{"type": "object", "properties":
    {...}}` so what the model receives is always valid.

    Idempotent: the real invariant is "a mapping that declares `type: object`
    is already JSON Schema" — full stop, whether or not it also carries a
    `properties` key. A bare `{type: object}` (a valid no-arg tool schema) is
    returned with `properties` defaulted to `{}`; any other keys already
    present (`properties`, `required`, `additionalProperties`, ...) are kept
    exactly as written. So a YAML author who writes real JSON Schema is never
    rewritten out from under them.

    `None` (parameters omitted from YAML entirely) passes through as `None`
    so each register_* call's own default parameter set still applies.

    The shorthand has no way to express `required`; nothing is inferred, so
    a shorthand-normalized schema simply has no `required` key (valid JSON
    Schema — `required` is optional).

    Raises `InvalidToolParameters` if `parameters` is neither `None` nor a
    mapping — YAML can express `parameters: [a, b]` or a bare scalar just as
    easily as a mapping, and blindly calling `.get()` on it would raise
    `AttributeError` and take the whole agent down with it (caught by
    `load_agents`'s broad `except`, but that degrades an agent to `draft`
    over one malformed tool declaration). The caller in the tools loop of
    `_build_agent` catches this and treats it like any other unsupported tool
    shape: warns, naming the agent and the tool, and skips just that tool.

    Lives in `core/`, not in ToolRegistry.register_client_tool, because this
    is where YAML enters the runtime for every tool type — 'client' is the
    first to hit this bug because it's the first type where YAML-authored
    'parameters' reach the model verbatim, but 'agent' would hit the exact
    same bug the moment any YAML declares 'parameters' on an agent tool.
    A normalizer placed in register_client_tool would only ever cover
    client tools; this one is available to any branch of the tools loop
    that decides it needs it, and to the integrations manifest as well.
    """
    if parameters is None:
        return None
    if not isinstance(parameters, dict):
        raise InvalidToolParameters(type(parameters).__name__)
    if parameters.get("type") == "object":
        normalized = dict(parameters)
        normalized.setdefault("properties", {})
        return normalized
    return {"type": "object", "properties": parameters}
