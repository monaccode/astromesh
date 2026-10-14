"""Tests that Rust and Python guardrails produce identical results."""

import pytest

from astromesh.core.guardrails import GuardrailBlocked, GuardrailsEngine


def _redact(text, action="redact"):
    engine = GuardrailsEngine({"input": [{"type": "pii_detection", "action": action}]})
    return engine.check_input(text).text


class TestPiiRedaction:
    def test_email_redaction(self, use_native):
        result = _redact("Contact john@example.com for info")
        assert "[REDACTED_EMAIL]" in result
        assert "john@example.com" not in result

    def test_phone_redaction(self, use_native):
        result = _redact("Call 555-123-4567 now")
        assert "[REDACTED_PHONE]" in result

    def test_ssn_redaction(self, use_native):
        result = _redact("SSN: 123-45-6789")
        assert "[REDACTED_SSN]" in result

    def test_cc_redaction(self, use_native):
        result = _redact("Card: 4111 1111 1111 1111")
        assert "[REDACTED_CC]" in result

    def test_no_pii(self, use_native):
        text = "This is a normal text with no PII."
        assert _redact(text) == text

    def test_action_not_redact(self, use_native):
        text = "Contact john@example.com"
        assert _redact(text, action="warn") == text


class TestTopicFilter:
    def test_blocked_topic_raises(self, use_native):
        engine = GuardrailsEngine(
            {"input": [{"type": "topic_filter", "blocked_topics": ["violence"], "action": "block"}]}
        )
        with pytest.raises(GuardrailBlocked, match="blocked topic"):
            engine.check_input("Let's discuss violence in media")

    def test_no_blocked_topic(self, use_native):
        engine = GuardrailsEngine(
            {"input": [{"type": "topic_filter", "blocked_topics": ["violence"], "action": "block"}]}
        )
        result = engine.check_input("Let's discuss cooking recipes")
        assert result.text == "Let's discuss cooking recipes"
