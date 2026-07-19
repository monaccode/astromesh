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
