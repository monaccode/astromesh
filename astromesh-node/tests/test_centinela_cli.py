from pathlib import Path

import yaml

from astromesh_node.cli.commands import centinela

LOCK = {
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
            "revisions": {"v0.1": {"version": "v0.1", "sha": "abc123", "gate": "passed"}},
        }
    ],
}

BINDINGS = {
    "apiVersion": "astromesh/v1",
    "kind": "CentinelaBindings",
    "metadata": {"name": "default"},
    "spec": {
        "bindings": [
            {"model": "centinela-sentiment", "alias": "prod", "endpoint": "https://ep.example.cloud"}
        ]
    },
}


def test_reconcile_command_writes_provider_config(tmp_path, monkeypatch):
    monkeypatch.setattr(centinela, "_load_lock", lambda: LOCK)
    bindings_path = tmp_path / "bindings.yaml"
    bindings_path.write_text(yaml.safe_dump(BINDINGS))
    out_path = tmp_path / "providers.centinela.yaml"

    centinela.reconcile_command(bindings=str(bindings_path), out=str(out_path))

    doc = yaml.safe_load(out_path.read_text())
    assert doc["kind"] == "ProviderConfig"
    entry = doc["spec"]["providers"]["centinela-sentiment"]
    assert entry["type"] == "centinela"
    assert entry["endpoint"] == "https://ep.example.cloud"
    assert entry["contract"]["labels"] == ["positivo", "neutral", "negativo"]


def test_reconcile_command_end_to_end_with_shipped_lock(tmp_path):
    # No monkeypatch: exercises real _load_lock() reading nebula's shipped catalog.lock.json,
    # plus the real seed bindings. Proves nebula is importable in astromesh-node's env.
    repo_root = Path(__file__).resolve().parents[2]
    seed_bindings = repo_root / "config" / "centinela" / "bindings.yaml"
    out_path = tmp_path / "providers.centinela.yaml"

    centinela.reconcile_command(bindings=str(seed_bindings), out=str(out_path))

    doc = yaml.safe_load(out_path.read_text())
    assert "centinela-sentiment" in doc["spec"]["providers"]
    assert doc["spec"]["providers"]["centinela-sentiment"]["type"] == "centinela"


def test_plugin_registers_centinela():
    import typer

    from astromesh_node.cli import plugin

    app = typer.Typer()
    plugin.register(app)
    names = {g.name for g in app.registered_groups}
    assert "centinela" in names
