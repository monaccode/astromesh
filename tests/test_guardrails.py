import pytest
from astromesh.core.guardrails import GuardrailsEngine


async def test_pii_redaction_email():
    engine = GuardrailsEngine(config={
        "input": [{"type": "pii_detection", "action": "redact"}]
    })
    result = await engine.apply_input("My email is john@example.com")
    assert "john@example.com" not in result
    assert "[REDACTED_EMAIL]" in result


async def test_pii_redaction_phone():
    engine = GuardrailsEngine(config={
        "input": [{"type": "pii_detection", "action": "redact"}]
    })
    result = await engine.apply_input("Call me at 555-123-4567")
    assert "555-123-4567" not in result
    assert "[REDACTED_PHONE]" in result


async def test_topic_filter_warn():
    engine = GuardrailsEngine(config={
        "input": [{"type": "topic_filter", "blocked_topics": ["competitor"]}]
    })
    result = await engine.apply_input("Tell me about competitor products")
    assert result is not None


async def test_topic_filter_block():
    engine = GuardrailsEngine(config={
        "input": [{"type": "topic_filter", "blocked_topics": ["secret"], "action": "block"}]
    })
    with pytest.raises(ValueError, match="Blocked topic"):
        await engine.apply_input("Tell me the secret")


async def test_output_cost_limit():
    engine = GuardrailsEngine(config={
        "output": [{"type": "cost_limit", "max_tokens_per_turn": 10}]
    })
    long_text = " ".join(["word"] * 100)
    result = await engine.apply_output(long_text)
    assert len(result) < len(long_text)
    assert "[truncated]" in result


async def test_no_guardrails():
    engine = GuardrailsEngine()
    result = await engine.apply_input("hello")
    assert result == "hello"
    result = await engine.apply_output("world")
    assert result == "world"
