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


@dataclass
class GuardrailResult:
    passed: bool
    text: str
    warnings: list[str] = field(default_factory=list)
    blocked: bool = False
    reason: str = ""


class GuardrailsEngine:
    """Input/output guardrails for agent safety."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._input_rules = self._config.get("input", [])
        self._output_rules = self._config.get("output", [])

    async def apply_input(self, text: str) -> str:
        result = text
        for rule in self._input_rules:
            rule_type = rule.get("type", "")
            if rule_type == "pii_detection":
                result = self._redact_pii(result, rule.get("action", "redact"))
            elif rule_type == "topic_filter":
                blocked = rule.get("blocked_topics", [])
                if _HAS_NATIVE_GUARDRAILS and not os.environ.get("ASTROMESH_FORCE_PYTHON"):
                    tf = RustTopicFilter(blocked)
                    found = tf.contains_blocked(result)
                    if found is not None:
                        if rule.get("action", "warn") == "block":
                            raise ValueError(f"Blocked topic detected: {found}")
                else:
                    for topic in blocked:
                        if topic.lower() in result.lower():
                            if rule.get("action", "warn") == "block":
                                raise ValueError(f"Blocked topic detected: {topic}")
                            result = result  # warn but allow
            elif rule_type == "max_length":
                max_len = rule.get("max_chars", 10000)
                if len(result) > max_len:
                    result = result[:max_len]
        return result

    async def apply_output(self, text: str) -> str:
        result = text
        for rule in self._output_rules:
            rule_type = rule.get("type", "")
            if rule_type == "pii_detection":
                result = self._redact_pii(result, rule.get("action", "redact"))
            elif rule_type == "cost_limit":
                max_tokens = rule.get("max_tokens_per_turn", 500)
                words = result.split()
                approx_tokens = len(words) * 1.3
                if approx_tokens > max_tokens:
                    keep = int(max_tokens / 1.3)
                    result = " ".join(words[:keep]) + "... [truncated]"
            elif rule_type == "content_filter":
                patterns = rule.get("blocked_patterns", [])
                for pattern in patterns:
                    result = re.sub(pattern, "[FILTERED]", result, flags=re.IGNORECASE)
        return result

    def _redact_pii(self, text: str, action: str) -> str:
        if action != "redact":
            return text
        if _HAS_NATIVE_GUARDRAILS and not os.environ.get("ASTROMESH_FORCE_PYTHON"):
            return _NATIVE_PII.redact(text)
        # Email
        text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[REDACTED_EMAIL]", text)
        # Phone (US format)
        text = re.sub(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[REDACTED_PHONE]", text)
        # SSN
        text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]", text)
        # Credit card (basic)
        text = re.sub(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "[REDACTED_CC]", text)
        return text
