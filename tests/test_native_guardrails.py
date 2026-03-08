"""Tests that Rust and Python guardrails produce identical results."""
import pytest


class TestPiiRedaction:
    def test_email_redaction(self, use_native):
        from astromesh.core.guardrails import GuardrailsEngine
        engine = GuardrailsEngine({"input": [{"type": "pii_detection", "action": "redact"}]})
        result = engine._redact_pii("Contact john@example.com for info", "redact")
        assert "[REDACTED_EMAIL]" in result
        assert "john@example.com" not in result

    def test_phone_redaction(self, use_native):
        from astromesh.core.guardrails import GuardrailsEngine
        engine = GuardrailsEngine()
        result = engine._redact_pii("Call 555-123-4567 now", "redact")
        assert "[REDACTED_PHONE]" in result

    def test_ssn_redaction(self, use_native):
        from astromesh.core.guardrails import GuardrailsEngine
        engine = GuardrailsEngine()
        result = engine._redact_pii("SSN: 123-45-6789", "redact")
        assert "[REDACTED_SSN]" in result

    def test_cc_redaction(self, use_native):
        from astromesh.core.guardrails import GuardrailsEngine
        engine = GuardrailsEngine()
        result = engine._redact_pii("Card: 4111 1111 1111 1111", "redact")
        assert "[REDACTED_CC]" in result

    def test_no_pii(self, use_native):
        from astromesh.core.guardrails import GuardrailsEngine
        engine = GuardrailsEngine()
        text = "This is a normal text with no PII."
        result = engine._redact_pii(text, "redact")
        assert result == text

    def test_action_not_redact(self, use_native):
        from astromesh.core.guardrails import GuardrailsEngine
        engine = GuardrailsEngine()
        text = "Contact john@example.com"
        result = engine._redact_pii(text, "warn")
        assert result == text


class TestTopicFilter:
    @pytest.mark.asyncio
    async def test_blocked_topic_raises(self, use_native):
        from astromesh.core.guardrails import GuardrailsEngine
        engine = GuardrailsEngine({
            "input": [{"type": "topic_filter", "blocked_topics": ["violence"], "action": "block"}]
        })
        with pytest.raises(ValueError, match="Blocked topic detected"):
            await engine.apply_input("Let's discuss violence in media")

    @pytest.mark.asyncio
    async def test_no_blocked_topic(self, use_native):
        from astromesh.core.guardrails import GuardrailsEngine
        engine = GuardrailsEngine({
            "input": [{"type": "topic_filter", "blocked_topics": ["violence"], "action": "block"}]
        })
        result = await engine.apply_input("Let's discuss cooking recipes")
        assert result == "Let's discuss cooking recipes"
