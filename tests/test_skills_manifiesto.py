"""`spec.skills`: el manifiesto declara lo que el agente sabe hacer (A2A Agent Cards)."""

import copy
import json
import logging
from pathlib import Path

import pytest
import yaml

from astromesh.api.routes import agents as agents_route
from astromesh.runtime.engine import AgentRuntime

BASE = yaml.safe_load(Path("config/agents/okf-demo.agent.yaml").read_text())

SKILL = {
    "id": "resumir",
    "name": "Resumir",
    "description": "Resume un texto",
    "tags": ["texto"],
    "examples": ["Resumí esto"],
    "inputModes": ["text/plain"],
    "outputModes": ["text/plain"],
}


def _build(skills):
    cfg = copy.deepcopy(BASE)
    if skills is not None:
        cfg["spec"]["skills"] = skills
    return AgentRuntime(config_dir="./config")._build_agent(cfg)


def test_skills_se_leen():
    assert _build([SKILL]).skills == [SKILL]


def test_sin_skills_es_lista_vacia():
    assert _build(None).skills == []


def test_skills_invalidas_se_omiten(caplog):
    sin_id = {"name": "X", "description": "d"}
    tipo_malo = {"id": "a", "name": "A", "description": "d", "tags": "no-lista"}
    with caplog.at_level(logging.WARNING):
        agent = _build([sin_id, SKILL, tipo_malo, "texto"])
    assert agent.skills == [SKILL]
    assert caplog.text.count("skill") >= 3


def test_skills_no_lista_se_ignora(caplog):
    with caplog.at_level(logging.WARNING):
        assert _build({"id": "x"}).skills == []
    assert "skills" in caplog.text


async def test_get_agent_devuelve_skills():
    agent = _build([SKILL])
    runtime = AgentRuntime(config_dir="./config")
    runtime._agents[agent.name] = agent
    agents_route.set_runtime(runtime)
    try:
        body = await agents_route.get_agent(agent.name)
        assert body["spec"]["skills"] == [SKILL]
        runtime._agent_configs[agent.name] = copy.deepcopy(BASE)
        body = await agents_route.get_agent(agent.name)
        assert body["spec"]["skills"] == [SKILL]
    finally:
        agents_route.set_runtime(None)


def test_schema_acepta_skills():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(Path("vscode-extension/schemas/agent.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    cfg = copy.deepcopy(BASE)
    cfg["spec"]["skills"] = [SKILL]
    assert not list(validator.iter_errors(cfg))
    cfg["spec"]["skills"] = [{"id": "a", "name": "A"}]
    assert list(validator.iter_errors(cfg))


def test_skill_con_campos_en_blanco_se_omite():
    en_blanco = {"id": "  ", "name": "A", "description": "d"}
    assert _build([en_blanco, SKILL]).skills == [SKILL]


def test_schema_acepta_a2a_de_nexus():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(Path("vscode-extension/schemas/agent.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    cfg = copy.deepcopy(BASE)
    cfg["spec"]["a2a"] = {"publicar": True}
    assert not list(validator.iter_errors(cfg))
    cfg["spec"]["a2a"] = {"publicar": "si"}
    assert list(validator.iter_errors(cfg))
