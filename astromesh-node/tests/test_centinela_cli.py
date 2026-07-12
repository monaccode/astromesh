import json
from pathlib import Path

import pytest
import typer
import yaml

from astromesh.centinela.promote import STUB_ENDPOINT
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


def _rev(rev, gate="passed"):
    return {"version": rev, "sha": "a" * 40, "gate": gate,
            "eval": {"macro_f1": 0.9, "invalid_rate": 0.01}}


def _sentiment(aliases, revisions):
    return {"name": "centinela-sentiment", "kind": "classifier",
            "task": "text-classification", "vertical": "finanzas",
            "hf_repo": "astromesh/Centinela-Qwen3-4B",
            "contract": {"labels": ["positivo", "neutral", "negativo"]},
            "aliases": aliases, "revisions": revisions}


def _write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj) if name.endswith(".json") else yaml.safe_dump(obj))
    return p


def _bindings(entries):
    return {"apiVersion": "astromesh/v1", "kind": "CentinelaBindings",
            "metadata": {"name": "default"}, "spec": {"bindings": entries}}


def test_plan_promotion_happy_path_edits_and_body(tmp_path):
    old = {"schema_version": "1",
           "models": [_sentiment({"staging": "v0.1"}, {"v0.1": _rev("v0.1"), "v0.2": _rev("v0.2")})]}
    new = {"schema_version": "1",
           "models": [_sentiment({"staging": "v0.2"}, {"v0.1": _rev("v0.1"), "v0.2": _rev("v0.2")})]}
    vendored = _write(tmp_path, "vendored.json", old)
    new_lock = _write(tmp_path, "new.json", new)
    bindings = _write(tmp_path, "bindings.yaml",
                      _bindings([{"model": "centinela-sentiment", "alias": "staging",
                                  "endpoint": "https://ep.example.cloud"}]))
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text('centinela = ["astromesh-nebula>=0.1.0"]\n')
    body = tmp_path / "pr-body.md"
    labels = tmp_path / "labels.txt"

    centinela.plan_promotion_command(
        new_lock=str(new_lock), version="0.2.0", bindings=str(bindings),
        vendored_lock=str(vendored), pr_body=str(body), labels_out=str(labels),
        pyproject=[str(pyproj)])

    assert json.loads(vendored.read_text())["models"][0]["aliases"]["staging"] == "v0.2"
    assert "astromesh-nebula>=0.2.0" in pyproj.read_text()
    assert "Alias moves" in body.read_text()
    assert labels.read_text().strip() == "centinela:staging"


def test_plan_promotion_noop_writes_empty_body(tmp_path):
    lock = {"schema_version": "1", "models": [_sentiment({"prod": "v0.1"}, {"v0.1": _rev("v0.1")})]}
    vendored = _write(tmp_path, "vendored.json", lock)
    new_lock = _write(tmp_path, "new.json", lock)
    bindings = _write(tmp_path, "bindings.yaml", _bindings([]))
    body = tmp_path / "pr-body.md"

    centinela.plan_promotion_command(
        new_lock=str(new_lock), version="0.1.0", bindings=str(bindings),
        vendored_lock=str(vendored), pr_body=str(body), labels_out=str(tmp_path / "l.txt"),
        pyproject=[])

    assert body.read_text() == ""   # empty body → workflow skips the PR


def test_plan_promotion_missing_binding_appends_stub(tmp_path):
    old = {"schema_version": "1", "models": [_sentiment({}, {"v0.1": _rev("v0.1")})]}
    new = {"schema_version": "1", "models": [_sentiment({"staging": "v0.1"}, {"v0.1": _rev("v0.1")})]}
    vendored = _write(tmp_path, "vendored.json", old)
    new_lock = _write(tmp_path, "new.json", new)
    bindings_path = _write(tmp_path, "bindings.yaml", _bindings([]))
    body = tmp_path / "pr-body.md"

    centinela.plan_promotion_command(
        new_lock=str(new_lock), version="0.1.0", bindings=str(bindings_path),
        vendored_lock=str(vendored), pr_body=str(body), labels_out=str(tmp_path / "l.txt"),
        pyproject=[])

    doc = yaml.safe_load(bindings_path.read_text())
    stub = [b for b in doc["spec"]["bindings"] if b["alias"] == "staging"][0]
    assert stub["endpoint"] == STUB_ENDPOINT


def test_plan_promotion_blocked_exits_1_but_still_writes(tmp_path):
    old = {"schema_version": "1", "models": [_sentiment({"prod": "v0.1"}, {"v0.1": _rev("v0.1")})]}
    new = {"schema_version": "1", "models": [_sentiment({"prod": "v0.1"}, {})]}  # rev gone
    vendored = _write(tmp_path, "vendored.json", old)
    new_lock = _write(tmp_path, "new.json", new)
    bindings = _write(tmp_path, "bindings.yaml",
                      _bindings([{"model": "centinela-sentiment", "alias": "prod",
                                  "endpoint": "https://ep.example.cloud"}]))
    body = tmp_path / "pr-body.md"

    with pytest.raises(typer.Exit) as exc:
        centinela.plan_promotion_command(
            new_lock=str(new_lock), version="0.1.0", bindings=str(bindings),
            vendored_lock=str(vendored), pr_body=str(body), labels_out=str(tmp_path / "l.txt"),
            pyproject=[])
    assert exc.value.exit_code == 1
    assert "Blocked" in body.read_text()
