# tests/test_rag_schema.py
import json
from pathlib import Path

import yaml
from jsonschema import validate


def _schema():
    return json.loads(Path("vscode-extension/schemas/rag.schema.json").read_text())


def test_example_config_validates():
    doc = yaml.safe_load(Path("config/rag/product-knowledge.rag.yaml").read_text())
    validate(instance=doc, schema=_schema())


def test_unknown_backend_fails_schema():
    import pytest
    from jsonschema import ValidationError

    doc = {
        "apiVersion": "astromesh/v1",
        "kind": "RAGPipeline",
        "metadata": {"name": "x"},
        "spec": {"vector_store": {"backend": "not-a-backend"}},
    }
    with pytest.raises(ValidationError):
        validate(instance=doc, schema=_schema())
