from astromesh_adk.guardrails import normalize_guardrails_config


def test_none_returns_empty():
    assert normalize_guardrails_config(None) == {"input": [], "output": []}


def test_dict_with_lists():
    config = normalize_guardrails_config({
        "input": ["pii_detection", "topic_filter"],
        "output": ["pii_detection"],
    })
    assert len(config["input"]) == 2
    assert config["input"][0]["type"] == "pii_detection"
    assert config["input"][0]["action"] == "redact"
    assert config["input"][1]["type"] == "topic_filter"
    assert config["input"][1]["action"] == "block"


def test_dict_with_full_config():
    config = normalize_guardrails_config({
        "input": [{"type": "pii_detection", "action": "warn"}],
        "output": [],
    })
    assert config["input"][0]["action"] == "warn"


def test_only_input():
    config = normalize_guardrails_config({"input": ["max_length"]})
    assert config["output"] == []
