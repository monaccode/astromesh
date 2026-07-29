"""Parseo de spec.chain del YAML del agente."""

import pytest

from astromesh.chain.models import ChainSpec


def test_parseo_minimo():
    spec = ChainSpec.from_dict({"on_complete": [{"agent": "b"}]})
    assert spec.mode == "sequential"
    assert spec.max_depth == 5
    assert len(spec.links) == 1
    assert spec.links[0].agent == "b"
    assert spec.links[0].when is None
    assert spec.links[0].default is False


def test_input_por_defecto():
    """Un eslabón sin `input` recibe la answer del agente anterior."""
    spec = ChainSpec.from_dict({"on_complete": [{"agent": "b"}]})
    assert spec.links[0].input == "{{ output.answer }}"


def test_input_explicito_gana():
    spec = ChainSpec.from_dict({"on_complete": [{"agent": "b", "input": "{{ output.data.x }}"}]})
    assert spec.links[0].input == "{{ output.data.x }}"


def test_modo_paralelo():
    spec = ChainSpec.from_dict({"mode": "parallel", "on_complete": [{"agent": "b"}]})
    assert spec.mode == "parallel"


def test_modo_invalido():
    with pytest.raises(ValueError, match="mode"):
        ChainSpec.from_dict({"mode": "turbo", "on_complete": [{"agent": "b"}]})


def test_campos_de_step_spec_pasan():
    spec = ChainSpec.from_dict(
        {
            "on_complete": [
                {
                    "agent": "b",
                    "when": "{{ output.data.score > 7 }}",
                    "retry": {"max_attempts": 3, "backoff": "exponential"},
                    "timeout_seconds": 30,
                    "on_error": "continue",
                }
            ]
        }
    )
    link = spec.links[0]
    assert link.when == "{{ output.data.score > 7 }}"
    assert link.retry == {"max_attempts": 3, "backoff": "exponential"}
    assert link.timeout_seconds == 30
    assert link.on_error == "continue"


def test_regla_default():
    spec = ChainSpec.from_dict({"on_complete": [{"agent": "b", "default": True}]})
    assert spec.links[0].default is True


def test_default_con_when_es_invalido():
    with pytest.raises(ValueError, match="default"):
        ChainSpec.from_dict({"on_complete": [{"agent": "b", "default": True, "when": "{{ x }}"}]})


def test_dos_defaults_es_invalido():
    with pytest.raises(ValueError, match="default"):
        ChainSpec.from_dict(
            {"on_complete": [{"agent": "b", "default": True}, {"agent": "c", "default": True}]}
        )


def test_eslabon_sin_agent_es_invalido():
    with pytest.raises(ValueError, match="agent"):
        ChainSpec.from_dict({"on_complete": [{"when": "{{ x }}"}]})


def test_on_complete_vacio_es_invalido():
    with pytest.raises(ValueError, match="on_complete"):
        ChainSpec.from_dict({"on_complete": []})


def test_max_depth_debe_ser_positivo():
    with pytest.raises(ValueError, match="max_depth"):
        ChainSpec.from_dict({"max_depth": 0, "on_complete": [{"agent": "b"}]})


def test_when_que_referencia_hermano_en_paralelo_es_invalido():
    """En paralelo todas las guardas se evalúan antes de arrancar cualquier rama."""
    with pytest.raises(ValueError, match="steps\\."):
        ChainSpec.from_dict(
            {
                "mode": "parallel",
                "on_complete": [
                    {"agent": "b"},
                    {"agent": "c", "when": "{{ steps.b.output.answer }}"},
                ],
            }
        )


def test_when_que_referencia_hermano_en_secuencial_es_valido():
    spec = ChainSpec.from_dict(
        {"on_complete": [{"agent": "b"}, {"agent": "c", "when": "{{ steps.b.output.answer }}"}]}
    )
    assert len(spec.links) == 2
