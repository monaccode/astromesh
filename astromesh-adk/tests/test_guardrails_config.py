from astromesh.core.guardrails import GuardrailsEngine

from astromesh_adk.guardrails import normalize_guardrails_config


def test_none_returns_empty():
    assert normalize_guardrails_config(None) == {"input": [], "output": []}


def test_shorthand_leaves_the_action_to_core():
    config = normalize_guardrails_config(
        {"input": ["pii_detection", "max_length"], "output": ["pii_detection"]}
    )
    assert config["input"] == [{"type": "pii_detection"}, {"type": "max_length"}]
    engine = GuardrailsEngine(config)
    # core 0.70 defaults: pii redacts, max_length truncates at 10000
    assert engine.check_input("mail me at a@b.co").text == "mail me at [REDACTED_EMAIL]"
    assert len(engine.check_input("x" * 10001).text) == 10000


def test_dict_with_full_config():
    config = normalize_guardrails_config(
        {"input": [{"type": "pii_detection", "action": "warn"}], "output": []}
    )
    assert config["input"][0]["action"] == "warn"


def test_only_input():
    config = normalize_guardrails_config({"input": ["max_length"]})
    assert config["output"] == []
