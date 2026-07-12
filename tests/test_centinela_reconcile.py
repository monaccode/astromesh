import pytest

from astromesh.centinela.reconcile import ReconcileError, reconcile, to_provider_config


def _lock() -> dict:
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
                    "v0.1": {"version": "v0.1", "sha": "abc123", "gate": "passed"},
                    "v0.2": {"version": "v0.2", "sha": "def456", "gate": "pending"},
                },
            },
            {
                "name": "centinela-chat",
                "kind": "instruct",
                "task": "text-generation",
                "vertical": "finanzas",
                "hf_repo": "astromesh/Centinela-Chat",
                "contract": {},
                "aliases": {"prod": "v1"},
                "revisions": {"v1": {"version": "v1", "sha": "c0ffee", "gate": "passed"}},
            },
            {
                "name": "centinela-topic",
                "kind": "classifier",
                "task": "text-classification",
                "vertical": "finanzas",
                "hf_repo": "astromesh/Centinela-Topic",
                "contract": {"labels": ["gasto", "ingreso"]},
                "aliases": {"prod": "v1"},
                "revisions": {"v1": {"version": "v1", "sha": "t0p1c", "gate": "passed"}},
            },
        ],
    }


def _bindings(model="centinela-sentiment", alias="prod"):
    return {
        "apiVersion": "astromesh/v1",
        "kind": "CentinelaBindings",
        "metadata": {"name": "default"},
        "spec": {
            "bindings": [{"model": model, "alias": alias, "endpoint": "https://ep.example.cloud"}]
        },
    }


def test_reconcile_happy_path():
    out = reconcile(_lock(), _bindings())
    assert out == {
        "centinela-sentiment": {
            "type": "centinela",
            "endpoint": "https://ep.example.cloud",
            "models": ["centinela-sentiment"],
            "kind": "classifier",
            "contract": {"labels": ["positivo", "neutral", "negativo"]},
            "revision": "v0.1",
            "sha": "abc123",
        }
    }


def test_reconcile_unknown_model_raises():
    with pytest.raises(ReconcileError, match="unknown model"):
        reconcile(_lock(), _bindings(model="nope"))


def test_reconcile_unknown_alias_raises():
    with pytest.raises(ReconcileError, match="alias"):
        reconcile(_lock(), _bindings(alias="staging"))


def test_reconcile_non_passed_gate_raises():
    lock = _lock()
    lock["models"][0]["aliases"]["prod"] = "v0.2"  # gate pending
    with pytest.raises(ReconcileError, match="gate"):
        reconcile(lock, _bindings())


def test_reconcile_instruct_kind_raises():
    with pytest.raises(ReconcileError, match="hf_tgi"):
        reconcile(_lock(), _bindings(model="centinela-chat"))


def test_reconcile_is_sorted():
    bindings = {
        "spec": {
            "bindings": [
                {
                    "model": "centinela-topic",
                    "alias": "prod",
                    "endpoint": "https://b.example.cloud",
                },
                {
                    "model": "centinela-sentiment",
                    "alias": "prod",
                    "endpoint": "https://a.example.cloud",
                },
            ]
        }
    }
    out = reconcile(_lock(), bindings)
    # input order is [topic, sentiment]; output must be sorted -> [sentiment, topic]
    assert list(out.keys()) == ["centinela-sentiment", "centinela-topic"]
    assert list(out.keys()) == sorted(out.keys())


def test_to_provider_config_wraps():
    providers = reconcile(_lock(), _bindings())
    doc = to_provider_config(providers)
    assert doc["apiVersion"] == "astromesh/v1"
    assert doc["kind"] == "ProviderConfig"
    assert doc["spec"]["providers"] == providers


def test_reconcile_tolerates_binding_without_endpoint():
    lock = _lock()
    bindings = {
        "apiVersion": "astromesh/v1",
        "kind": "CentinelaBindings",
        "metadata": {"name": "default"},
        "spec": {
            "bindings": [
                {
                    "model": "centinela-sentiment",
                    "alias": "prod",
                    "serving": {"instance_type": "nvidia-a10g"},
                }
            ]
        },
    }
    out = reconcile(lock, bindings)
    assert out["centinela-sentiment"]["type"] == "centinela"
    assert out["centinela-sentiment"]["endpoint"] is None
