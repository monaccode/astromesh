"""The VS Code agent schema must agree with what the runtime actually does.

Every bug in this area had the same shape: the schema and the runtime disagreed,
and nothing compared them. `timeout` and `parameters` were real keys the wiring
dropped; `vllm`/`llamacpp`/`huggingface`/`onnx` were sources the schema offered
and `build_candidate_provider` had no branch for; `roles`/`default` were a whole
shipped feature the schema rejected. Each was found by hand, one at a time.

These tests close both directions: the schema must accept every agent the repo
ships, and it must not advertise a source the engine cannot build.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

jsonschema = pytest.importorskip("jsonschema")

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "vscode-extension" / "schemas" / "agent.schema.json"
AGENT_DIR = REPO_ROOT / "config" / "agents"
AGENT_FILES = sorted(AGENT_DIR.glob("*.agent.yaml"))


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def test_schema_is_itself_valid(schema):
    jsonschema.Draft202012Validator.check_schema(schema)


def test_repo_ships_agents_to_validate():
    """Guard the parametrization below: an empty glob would make it vacuous."""
    assert AGENT_FILES, f"no agent YAML found under {AGENT_DIR}"


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.name)
def test_shipped_agent_validates_against_schema(schema, path):
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(yaml.safe_load(path.read_text())), key=lambda e: e.path)
    assert not errors, "\n".join(f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors)


def test_schema_advertises_only_sources_the_engine_can_build(schema):
    """A source in the enum with no branch in build_candidate_provider passes the
    editor and then returns None at runtime — 'not registered; skipping'."""
    from astromesh.runtime.engine import _CONSUMED_KEYS

    wired = set(_CONSUMED_KEYS)
    for key in ("source", "provider"):
        advertised = set(schema["$defs"]["modelConfig"]["properties"][key]["enum"])
        assert advertised <= wired, f"{key}: schema offers unwired source(s) {advertised - wired}"


def test_schema_declares_every_key_the_engine_consumes(schema):
    """The mirror case: a key the wiring reads but the schema forbids is flagged
    in-editor even though it works — which is how `timeout` looked."""
    from astromesh.runtime.engine import _CONSUMED_KEYS

    declared = set(schema["$defs"]["modelConfig"]["properties"])
    consumed = set().union(*_CONSUMED_KEYS.values())
    assert consumed <= declared, f"schema is missing consumed key(s) {consumed - declared}"


def _pipeline(stages) -> dict:
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "pipe", "version": "0.1.0"},
        "spec": {
            "identity": {"description": "d"},
            "model": {"primary": {"provider": "ollama", "model": "llama3"}},
            "prompts": {"system": "s"},
            "orchestration": {"pattern": "pipeline", "stages": stages},
        },
    }


def test_pipeline_stages_validan_como_las_acepta_el_engine(schema):
    """`orchestration.stages` entró en 0.65.0 (engine.py, rama pipeline) sin su clave en el
    schema, que con `additionalProperties: false` rechazaba un pipeline válido."""
    validator = jsonschema.Draft202012Validator(schema)
    assert not list(validator.iter_errors(_pipeline(["leer", "resumir"])))
    assert list(validator.iter_errors(_pipeline(["solo"])))
    assert list(validator.iter_errors(_pipeline(["x" * 41, "y"])))


def _agente_con_tool(tool: dict) -> dict:
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "a2a-demo"},
        "spec": {
            "identity": {"display_name": "A2A demo"},
            "model": {"primary": {"provider": "ollama", "model": "llama3"}},
            "prompts": {"system": "hola"},
            "tools": [tool],
        },
    }


def test_schema_acepta_tool_a2a(schema):
    validator = jsonschema.Draft202012Validator(schema)

    def errores(tool):
        return list(validator.iter_errors(_agente_con_tool(tool)))

    base = {"name": "agenda", "type": "a2a", "card_url": "https://x.example/card.json"}
    completa = {
        **base,
        "auth": {"bearer_env": "AGENDA_TOKEN"},
        "policy": {
            "max_bytes": 262144,
            "timeout": 30,
            "accept_parts": ["text", "data"],
            "allow_insecure_http": False,
        },
        "description": "Agenda externa",
        "max_result_tokens": 500,
    }
    assert not errores(base)
    assert not errores(completa)

    sin_card = {k: v for k, v in base.items() if k != "card_url"}
    assert errores(sin_card)
    assert errores({**base, "auth": {"api_key_env": "A", "bearer_env": "B"}})
    assert errores({**base, "auth": {}})
    assert errores({**base, "auth": {"api_key_env": "no-valido!"}})
    assert errores({**base, "auth": {"api_key": "sk-literal"}})
    assert errores({**base, "policy": {"allowed": ["x"]}})
    assert errores({**base, "policy": {"max_bytes": 16 * 1024 * 1024 + 1}})
    assert errores({**base, "policy": {"timeout": 0}})
    assert errores({**base, "policy": {"timeout": 601}})
    assert errores({**base, "policy": {"accept_parts": []}})
    assert errores({**base, "policy": {"accept_parts": ["video"]}})
    assert errores({**base, "parameters": {"q": {"type": "string"}}})
