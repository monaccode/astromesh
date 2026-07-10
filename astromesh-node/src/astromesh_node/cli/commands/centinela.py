"""astromeshctl centinela — reconcile Centinela bindings into provider config."""

import json
from importlib.resources import files
from pathlib import Path

import typer
import yaml

from astromesh.centinela.reconcile import reconcile, to_provider_config
from astromesh_node.cli.output import console

app = typer.Typer(help="Centinela model provider management.")


def _load_lock() -> dict:
    """Read the compiled catalog lock shipped inside the astromesh-nebula wheel."""
    text = (files("nebula") / "catalog.lock.json").read_text(encoding="utf-8")
    return json.loads(text)


@app.command("reconcile")
def reconcile_command(
    bindings: str = typer.Option(
        "./config/centinela/bindings.yaml", "--bindings", help="Path to bindings.yaml"
    ),
    out: str = typer.Option(
        "./config/providers.centinela.yaml", "--out", help="Output ProviderConfig path"
    ),
) -> None:
    """Compile bindings + catalog lock into provider config (compile-only; no HF calls)."""
    lock = _load_lock()
    bindings_doc = yaml.safe_load(Path(bindings).read_text())
    providers = reconcile(lock, bindings_doc)
    doc = to_provider_config(providers)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(yaml.safe_dump(doc, sort_keys=True, allow_unicode=True))
    console.print(f"[green]Reconciled[/green] {len(providers)} Centinela provider(s) -> {out}")
