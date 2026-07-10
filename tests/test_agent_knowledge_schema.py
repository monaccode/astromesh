"""Agent schema accepts the spec.knowledge block that the runtime resolves (RAG wiring)."""
import json
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate


def _schema():
    return json.loads(Path("vscode-extension/schemas/agent.schema.json").read_text())


def _agent(knowledge):
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "kb-agent", "version": "1.0.0"},
        "spec": {
            "identity": {"display_name": "KB Agent"},
            "model": {"primary": {"provider": "ollama", "model": "llama3.1:8b"}},
            "prompts": {"system": "Use the knowledge base."},
            "orchestration": {"pattern": "react"},
            "knowledge": knowledge,
        },
    }


def test_agent_with_knowledge_pipeline_validates():
    validate(instance=_agent({"pipeline": "product-knowledge", "top_k": 5}), schema=_schema())


def test_agent_knowledge_without_pipeline_fails():
    with pytest.raises(ValidationError):
        validate(instance=_agent({"top_k": 5}), schema=_schema())


def test_agent_knowledge_rejects_unknown_key():
    with pytest.raises(ValidationError):
        validate(instance=_agent({"pipeline": "pk", "strategey": "oops"}), schema=_schema())
