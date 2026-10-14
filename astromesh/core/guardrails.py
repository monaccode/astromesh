"""Guardrails de entrada y salida de un agente (`spec.guardrails`).

`GuardrailsEngine(config, agent_name)` se construye una vez por agente y
normaliza las reglas: lo que no entiende lo descarta con un warning, nunca
impide que el agente cargue. `Agent.run` llama `check_input` antes de memoria y
modelo, `check_output` sobre la respuesta, `filter_stream` sobre cada evento
`token` y `check_budget` antes de cada llamada al modelo.

Bloquear es levantar `GuardrailBlocked`; `Agent.run` la convierte en una
respuesta de rechazo (`blocked: True`), no en un error.
"""

import logging
import os
import re
from dataclasses import dataclass, field

try:
    from astromesh._native import RustPiiRedactor, RustTopicFilter

    _NATIVE_PII = RustPiiRedactor()
    _HAS_NATIVE_GUARDRAILS = True
except ImportError:
    _NATIVE_PII = None
    _HAS_NATIVE_GUARDRAILS = False

logger = logging.getLogger(__name__)

DEFAULT_MESSAGE = "I can't help with that request."

# Mismos patrones y etiquetas que `native/src/guardrails.rs`. Formato de EE. UU.:
# un teléfono argentino no se detecta (límite documentado).
_PII_PATTERNS = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[REDACTED_CC]"),
)

# tipo -> (direcciones, acciones con la default primero, claves propias)
_RULES = {
    "pii_detection": (("input", "output"), ("redact", "block", "warn"), set()),
    "topic_filter": (("input",), ("warn", "block"), {"blocked_topics", "forbidden_topics"}),
    "max_length": (("input",), ("truncate", "block"), {"max_chars", "max_characters"}),
    "content_filter": (
        ("output",),
        ("redact", "block"),
        {"blocked_patterns", "forbidden_keywords"},
    ),
    # Es de la corrida, no de una dirección: se acepta en cualquiera de las dos.
    "cost_limit": (("input", "output"), ("block",), {"max_tokens_per_turn", "count"}),
}
_COMMON_KEYS = {"type", "action", "message"}
_NEEDS_CLASSIFIER = {"blocked_categories", "allowed_topics"}


class GuardrailBlocked(Exception):
    """Una regla bloqueó la corrida. `reason` nunca repite el contenido bloqueado."""

    def __init__(self, direction: str, rule: str, reason: str, message: str):
        super().__init__(f"{direction} guardrail {rule}: {reason}")
        self.direction = direction
        self.rule = rule
        self.reason = reason
        self.message = message

    def as_dict(self) -> dict:
        return {"direction": self.direction, "rule": self.rule, "reason": self.reason}


@dataclass
class GuardrailReport:
    text: str
    rules: list[str] = field(default_factory=list)
    redactions: int = 0
    warnings: int = 0


def _native() -> bool:
    return _HAS_NATIVE_GUARDRAILS and not os.environ.get("ASTROMESH_FORCE_PYTHON")


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value) if isinstance(value, list | tuple) else []


def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _redact_pii(text: str) -> tuple[str, int]:
    if _native():
        redacted = _NATIVE_PII.redact(text)
        return redacted, redacted.count("[REDACTED_") - text.count("[REDACTED_")
    total = 0
    for pattern, tag in _PII_PATTERNS:
        text, n = pattern.subn(tag, text)
        total += n
    return text, total


def _find_topic(text: str, topics: list[str]) -> str | None:
    if _native():
        return RustTopicFilter(topics).contains_blocked(text)
    folded = text.casefold()
    return next((t for t in topics if t.casefold() in folded), None)


class GuardrailsEngine:
    def __init__(self, config: dict | None = None, agent_name: str = "agent"):
        self._agent = agent_name
        self._input: list[dict] = []
        self._output: list[dict] = []
        budgets: list[dict] = []
        if not isinstance(config, dict):
            logger.warning("agent %s: guardrails must be a mapping, ignored", agent_name)
            config = {}
        for direction in ("input", "output"):
            rules = config.get(direction) or []
            if not isinstance(rules, list):
                logger.warning(
                    "agent %s: guardrails.%s must be a list, ignored", agent_name, direction
                )
                continue
            for index, raw in enumerate(rules):
                rule = self._normalize(direction, index, raw)
                if rule is None:
                    continue
                if rule["type"] == "cost_limit":
                    budgets.append(rule)
                else:
                    (self._input if direction == "input" else self._output).append(rule)
        self.cost_limit = min(budgets, key=lambda r: r["max_tokens"]) if budgets else None

    @property
    def has_input(self) -> bool:
        return bool(self._input)

    @property
    def has_output(self) -> bool:
        return bool(self._output)

    def _warn(self, direction: str, index: int, msg: str) -> None:
        logger.warning("agent %s: guardrails.%s[%d]: %s", self._agent, direction, index, msg)

    def _normalize(self, direction: str, index: int, raw) -> dict | None:
        if not isinstance(raw, dict):
            self._warn(direction, index, "not a mapping, discarded")
            return None
        kind = raw.get("type")
        if kind not in _RULES:
            self._warn(direction, index, f"unknown type {kind!r}, discarded")
            return None
        directions, actions, keys = _RULES[kind]
        if direction not in directions:
            self._warn(direction, index, f"{kind} does not apply to {direction}, discarded")
            return None
        for key in sorted(raw.keys() - _COMMON_KEYS - keys):
            if key in _NEEDS_CLASSIFIER:
                self._warn(
                    direction,
                    index,
                    f"{key} needs a classifier; not supported, use blocked_patterns "
                    "or the system prompt",
                )
            else:
                self._warn(direction, index, f"unknown key {key!r} ignored")
        action = raw.get("action", actions[0])
        if action not in actions:
            self._warn(
                direction,
                index,
                f"action {action!r} not valid for {kind} ({', '.join(actions)}), discarded",
            )
            return None
        message = raw.get("message")
        if not isinstance(message, str) or not message.strip():
            message = DEFAULT_MESSAGE
        rule = {"type": kind, "action": action, "message": message}

        if kind == "topic_filter":
            topics = _as_list(raw.get("blocked_topics")) + _as_list(raw.get("forbidden_topics"))
            rule["topics"] = [str(t) for t in topics if str(t).strip()]
            if not rule["topics"]:
                self._warn(direction, index, "topic_filter with no topics, discarded")
                return None
        elif kind == "max_length":
            limit = raw.get("max_chars", raw.get("max_characters", 10000))
            if not _positive_int(limit):
                self._warn(direction, index, "max_chars must be a positive integer, discarded")
                return None
            rule["max_chars"] = limit
        elif kind == "content_filter":
            patterns = []
            for p in _as_list(raw.get("blocked_patterns")):
                try:
                    patterns.append(re.compile(str(p), re.IGNORECASE))
                except re.error as exc:
                    self._warn(direction, index, f"invalid regex {p!r} discarded: {exc}")
            patterns.extend(
                re.compile(re.escape(str(k)), re.IGNORECASE)
                for k in _as_list(raw.get("forbidden_keywords"))
                if str(k).strip()
            )
            if not patterns:
                self._warn(direction, index, "content_filter with no valid patterns, discarded")
                return None
            rule["patterns"] = patterns
        elif kind == "cost_limit":
            limit = raw.get("max_tokens_per_turn")
            if not _positive_int(limit):
                self._warn(
                    direction,
                    index,
                    "cost_limit needs max_tokens_per_turn as a positive integer, discarded",
                )
                return None
            count = raw.get("count", "output")
            if count not in ("output", "total"):
                self._warn(
                    direction, index, f"count {count!r} not valid (output, total), discarded"
                )
                return None
            rule["max_tokens"] = limit
            rule["count"] = count
        return rule

    def check_input(self, text: str) -> GuardrailReport:
        return self._apply("input", self._input, text)

    def check_output(self, text: str) -> GuardrailReport:
        return self._apply("output", self._output, text)

    def filter_stream(self, text: str) -> str | None:
        """El `content` de un evento `token` filtrado; None si una regla lo bloquea."""
        if not self._output:
            return text
        try:
            return self.check_output(text).text
        except GuardrailBlocked:
            return None

    def check_budget(self, counted: int) -> None:
        rule = self.cost_limit
        if rule is not None and counted >= rule["max_tokens"]:
            raise GuardrailBlocked(
                "run",
                "cost_limit",
                f"token budget {rule['max_tokens']} exceeded ({counted})",
                rule["message"],
            )

    def tokens_of(self, usage: dict | None) -> int:
        if self.cost_limit is None or not usage:
            return 0
        counted = usage.get("output_tokens", 0) or 0
        if self.cost_limit["count"] == "total":
            counted += usage.get("input_tokens", 0) or 0
        return int(counted)

    def _apply(self, direction: str, rules: list[dict], text: str) -> GuardrailReport:
        report = GuardrailReport(text=text)
        for rule in rules:
            kind, action = rule["type"], rule["action"]
            report.rules.append(kind)
            if kind == "pii_detection":
                redacted, found = _redact_pii(report.text)
                if found:
                    if action == "block":
                        raise GuardrailBlocked(direction, kind, "pii detected", rule["message"])
                    if action == "warn":
                        report.warnings += 1
                    else:
                        report.text = redacted
                        report.redactions += found
            elif kind == "topic_filter":
                if _find_topic(report.text, rule["topics"]) is not None:
                    if action == "block":
                        raise GuardrailBlocked(direction, kind, "blocked topic", rule["message"])
                    report.warnings += 1
            elif kind == "max_length":
                if len(report.text) > rule["max_chars"]:
                    if action == "block":
                        raise GuardrailBlocked(direction, kind, "input too long", rule["message"])
                    report.text = report.text[: rule["max_chars"]]
            elif kind == "content_filter":
                if action == "block":
                    if any(p.search(report.text) for p in rule["patterns"]):
                        raise GuardrailBlocked(direction, kind, "pattern matched", rule["message"])
                else:
                    for p in rule["patterns"]:
                        report.text, n = p.subn("[FILTERED]", report.text)
                        report.redactions += n
        return report
