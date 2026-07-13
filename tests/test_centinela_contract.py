"""Cross-repo guardian: astromesh validates the SAME lock against nebula's shipped schema."""

import pytest
from jsonschema import ValidationError

pytest.importorskip("nebula", reason="astromesh-nebula (optional sibling repo) not installed")

from nebula.catalog import validate_lock  # noqa: E402


def _valid_lock() -> dict:
    return {
        "schema_version": "1",
        "models": [
            {
                "name": "centinela-sentiment",
                "kind": "classifier",
                "task": "text-classification",
                "vertical": "finanzas",
                "hf_repo": "astromesh/Centinela-Qwen3-4B",
                "contract": {"labels": ["positivo", "neutral", "negativo"]},
                "aliases": {"prod": "v0.1"},
                "revisions": {
                    "v0.1": {
                        "version": "v0.1",
                        "sha": "abc123",
                        "eval": {"macro_f1": 0.9},
                        "gate": "passed",
                        "formats": ["safetensors"],
                        "dataset": "centinela-sentiment-es@1",
                        "train_config_hash": "sha256:deadbeef",
                        "base_model": "Qwen/Qwen3-4B",
                    }
                },
            }
        ],
    }


def test_astromesh_accepts_valid_lock():
    validate_lock(_valid_lock())  # must not raise


def test_astromesh_rejects_incompatible_lock():
    lock = _valid_lock()
    lock["models"][0]["revisions"]["v0.1"]["gate"] = "banana"  # not in enum
    with pytest.raises(ValidationError):
        validate_lock(lock)
