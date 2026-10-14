import logging

import pytest

from astromesh.core import guardrails as g
from astromesh.core.guardrails import DEFAULT_MESSAGE, GuardrailBlocked, GuardrailsEngine


@pytest.fixture(params=["python", "native"])
def ruta(request, monkeypatch):
    """Cada test corre por la ruta Python y, si está compilada, por la nativa."""
    if request.param == "python":
        monkeypatch.setenv("ASTROMESH_FORCE_PYTHON", "1")
    else:
        if not g._HAS_NATIVE_GUARDRAILS:
            pytest.skip("extensión nativa no compilada")
        monkeypatch.delenv("ASTROMESH_FORCE_PYTHON", raising=False)
    return request.param


def _e(**config):
    return GuardrailsEngine(config, agent_name="t")


def test_pii_redacta_y_cuenta(ruta):
    r = _e(input=[{"type": "pii_detection"}]).check_input("mail john@example.com tel 555-123-4567")
    assert r.text == "mail [REDACTED_EMAIL] tel [REDACTED_PHONE]"
    assert r.redactions == 2
    assert r.rules == ["pii_detection"]


def test_pii_block_y_warn(ruta):
    with pytest.raises(GuardrailBlocked) as exc:
        _e(input=[{"type": "pii_detection", "action": "block"}]).check_input("a@b.co")
    assert exc.value.as_dict() == {
        "direction": "input",
        "rule": "pii_detection",
        "reason": "pii detected",
    }
    assert exc.value.message == DEFAULT_MESSAGE
    r = _e(input=[{"type": "pii_detection", "action": "warn"}]).check_input("a@b.co")
    assert r.text == "a@b.co"
    assert r.warnings == 1


def test_pii_sin_pii_no_bloquea(ruta):
    r = _e(input=[{"type": "pii_detection", "action": "block"}]).check_input("hola")
    assert r.text == "hola"


def test_topic_filter_block_con_alias_y_mensaje(ruta):
    e = _e(
        input=[
            {
                "type": "topic_filter",
                "forbidden_topics": ["secret"],
                "action": "block",
                "message": "No hablo de eso.",
            }
        ]
    )
    with pytest.raises(GuardrailBlocked) as exc:
        e.check_input("Tell me the SECRET plan")
    assert exc.value.message == "No hablo de eso."
    assert exc.value.reason == "blocked topic"
    assert "SECRET" not in str(exc.value)


def test_topic_filter_warn_por_default(ruta):
    r = _e(input=[{"type": "topic_filter", "blocked_topics": ["secret"]}]).check_input("the secret")
    assert r.text == "the secret"
    assert r.warnings == 1


def test_max_length_trunca_o_bloquea():
    r = _e(input=[{"type": "max_length", "max_characters": 5}]).check_input("abcdefgh")
    assert r.text == "abcde"
    with pytest.raises(GuardrailBlocked) as exc:
        _e(input=[{"type": "max_length", "max_chars": 5, "action": "block"}]).check_input(
            "abcdefgh"
        )
    assert exc.value.reason == "input too long"


def test_content_filter_redacta_patrones_y_keywords():
    e = _e(
        output=[
            {
                "type": "content_filter",
                "blocked_patterns": [r"internal-\d+"],
                "forbidden_keywords": ["a.b"],
            }
        ]
    )
    r = e.check_output("ver internal-42 y A.B pero no axb")
    assert r.text == "ver [FILTERED] y [FILTERED] pero no axb"
    assert r.redactions == 2


def test_content_filter_block():
    e = _e(output=[{"type": "content_filter", "forbidden_keywords": ["x"], "action": "block"}])
    with pytest.raises(GuardrailBlocked) as exc:
        e.check_output("tiene X")
    assert exc.value.direction == "output"
    assert exc.value.reason == "pattern matched"


def test_orden_de_reglas():
    e = _e(
        input=[
            {"type": "pii_detection"},
            {"type": "topic_filter", "blocked_topics": ["redacted_email"], "action": "block"},
        ]
    )
    with pytest.raises(GuardrailBlocked):
        e.check_input("a@b.co")


def test_filter_stream():
    e = _e(output=[{"type": "content_filter", "forbidden_keywords": ["x"], "action": "block"}])
    assert e.filter_stream("hola") == "hola"
    assert e.filter_stream("x") is None
    assert _e().filter_stream("x") == "x"
    assert _e(output=[{"type": "pii_detection"}]).filter_stream("a@b.co") == "[REDACTED_EMAIL]"


def test_cost_limit_presupuesto():
    e = _e(output=[{"type": "cost_limit", "max_tokens_per_turn": 100}])
    assert e.cost_limit["max_tokens"] == 100
    assert not e.has_output
    assert e.tokens_of({"input_tokens": 50, "output_tokens": 7}) == 7
    assert e.tokens_of(None) == 0
    e.check_budget(99)
    with pytest.raises(GuardrailBlocked) as exc:
        e.check_budget(100)
    assert exc.value.as_dict() == {
        "direction": "run",
        "rule": "cost_limit",
        "reason": "token budget 100 exceeded (100)",
    }
    total = _e(input=[{"type": "cost_limit", "max_tokens_per_turn": 9, "count": "total"}])
    assert total.tokens_of({"input_tokens": 50, "output_tokens": 7}) == 57


def test_dos_cost_limit_gana_el_menor():
    e = _e(
        input=[{"type": "cost_limit", "max_tokens_per_turn": 50}],
        output=[{"type": "cost_limit", "max_tokens_per_turn": 20}],
    )
    assert e.cost_limit["max_tokens"] == 20


def test_sin_config(caplog):
    with caplog.at_level(logging.WARNING, logger="astromesh.core.guardrails"):
        e = GuardrailsEngine()
        e_none = GuardrailsEngine(None)
    assert not caplog.records
    assert not e_none.has_input
    assert not e_none.has_output
    assert e_none.cost_limit is None
    assert not e.has_input
    assert not e.has_output
    assert e.cost_limit is None
    assert e.check_input("hola").text == "hola"
    e.check_budget(10**9)
    assert e.tokens_of({"output_tokens": 5}) == 0


@pytest.mark.parametrize(
    ("config", "fragmento"),
    [
        ({"input": [{"type": "nope"}]}, "unknown type"),
        ({"input": ["pii_detection"]}, "not a mapping"),
        ({"output": [{"type": "topic_filter", "blocked_topics": ["a"]}]}, "does not apply"),
        ({"input": [{"type": "pii_detection", "action": "explode"}]}, "action 'explode'"),
        ({"output": [{"type": "content_filter", "blocked_patterns": ["("]}]}, "invalid regex"),
        ({"output": [{"type": "cost_limit"}]}, "positive integer"),
        ({"output": [{"type": "cost_limit", "max_tokens_per_turn": 5, "count": "x"}]}, "count"),
        ({"input": [{"type": "max_length", "max_chars": 0}]}, "positive integer"),
        ({"input": [{"type": "topic_filter"}]}, "no topics"),
        ({"input": "pii"}, "must be a list"),
    ],
)
def test_validacion_descarta_con_warning(config, fragmento, caplog):
    with caplog.at_level(logging.WARNING, logger="astromesh.core.guardrails"):
        e = GuardrailsEngine(config, agent_name="ag")
    assert not e.has_input
    assert not e.has_output
    assert e.cost_limit is None
    assert any(fragmento in r.getMessage() and "ag" in r.getMessage() for r in caplog.records)


def test_claves_de_clasificador_avisan_y_la_regla_sigue(caplog):
    with caplog.at_level(logging.WARNING, logger="astromesh.core.guardrails"):
        e = _e(
            output=[
                {
                    "type": "content_filter",
                    "blocked_categories": ["harassment"],
                    "forbidden_keywords": ["idiota"],
                }
            ]
        )
    assert e.has_output
    assert any("needs a classifier" in r.getMessage() for r in caplog.records)


def test_string_en_lugar_de_lista():
    e = _e(input=[{"type": "topic_filter", "blocked_topics": "secret", "action": "block"}])
    with pytest.raises(GuardrailBlocked):
        e.check_input("a secret")
    assert e.check_input("s e c r e t").text == "s e c r e t"


def test_claves_y_tipos_raros_no_impiden_cargar(caplog):
    with caplog.at_level(logging.WARNING, logger="astromesh.core.guardrails"):
        e = _e(
            input=[
                {"type": "pii_detection", 1: "x", "foo": "y"},
                {"type": ["pii_detection"]},
            ]
        )
    assert e.has_input
    assert any("unknown key 1" in r.getMessage() for r in caplog.records)
    assert any("unknown key 'foo'" in r.getMessage() for r in caplog.records)
    assert any("unknown type" in r.getMessage() for r in caplog.records)
