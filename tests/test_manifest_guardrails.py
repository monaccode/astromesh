"""Ningún manifiesto del repo declara guardrails que el motor descarte o no entienda."""

import logging
from pathlib import Path

import pytest
import yaml

from astromesh.core.guardrails import GuardrailsEngine

RAIZ = Path(__file__).resolve().parents[1] / "config"
ARCHIVOS = sorted([*RAIZ.glob("agents/*.agent.yaml"), *RAIZ.glob("templates/*.template.yaml")])


def _guardrails(nodo):
    if isinstance(nodo, dict):
        if "guardrails" in nodo:
            return nodo["guardrails"]
        for v in nodo.values():
            if (r := _guardrails(v)) is not None:
                return r
    if isinstance(nodo, list):
        for v in nodo:
            if (r := _guardrails(v)) is not None:
                return r
    return None


@pytest.mark.parametrize("archivo", ARCHIVOS, ids=lambda p: p.name)
def test_guardrails_del_manifiesto_sin_warnings(archivo, caplog):
    config = _guardrails(yaml.safe_load(archivo.read_text()))
    if config is None:
        pytest.skip("sin guardrails")
    with caplog.at_level(logging.WARNING, logger="astromesh.core.guardrails"):
        GuardrailsEngine(config, agent_name=archivo.name)
    assert not caplog.records, [r.getMessage() for r in caplog.records]
