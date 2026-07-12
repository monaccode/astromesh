"""astromeshctl centinela — reconcile Centinela bindings into provider config."""

import json
from importlib.resources import files
from pathlib import Path
from typing import Optional

import typer
import yaml

from astromesh.centinela.promote import (
    PromoteError,
    bump_nebula_pin,
    plan_promotion,
    pr_labels,
    render_pr_body,
    stub_binding,
)
from astromesh.centinela.reconcile import ReconcileError, reconcile, to_provider_config
from astromesh_node.cli.output import console, print_error

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
    try:
        providers = reconcile(lock, bindings_doc)
    except ReconcileError as exc:
        print_error(f"Reconcile failed: {exc}")
        raise typer.Exit(1) from exc
    doc = to_provider_config(providers)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(yaml.safe_dump(doc, sort_keys=True, allow_unicode=True))
    console.print(f"[green]Reconciled[/green] {len(providers)} Centinela provider(s) -> {out}")


def _apply_stub_bindings(bindings_path: Path, missing: list) -> None:
    """Append a stub binding for each missing (model, alias) to bindings.yaml."""
    doc = yaml.safe_load(bindings_path.read_text()) or {}
    doc.setdefault("spec", {}).setdefault("bindings", [])
    for mb in missing:
        doc["spec"]["bindings"].append(stub_binding(mb.model, mb.alias))
    bindings_path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))


def _apply_pin_bump(pyproject_paths: list[str], version: str) -> None:
    """Rewrite the astromesh-nebula pin in each given pyproject.toml."""
    for raw in pyproject_paths:
        p = Path(raw)
        if p.exists():
            p.write_text(bump_nebula_pin(p.read_text(), version))


@app.command("plan-promotion")
def plan_promotion_command(
    new_lock: str = typer.Option(..., "--new-lock", help="New catalog.lock.json from nebula"),
    version: str = typer.Option(..., "--version", help="Nebula version to pin"),
    bindings: str = typer.Option(
        "./config/centinela/bindings.yaml", "--bindings", help="Path to bindings.yaml"),
    vendored_lock: str = typer.Option(
        "./docs-site/src/data/catalog.lock.json", "--vendored-lock",
        help="Baseline (currently vendored) lock"),
    pr_body: str = typer.Option("./pr-body.md", "--pr-body", help="Where to write the PR body"),
    labels_out: str = typer.Option("./pr-labels.txt", "--labels-out", help="Where to write PR labels"),
    pyproject: Optional[list[str]] = typer.Option(
        None, "--pyproject", help="pyproject.toml(s) whose astromesh-nebula pin to bump"),
) -> None:
    """Plan a catalog promotion into file edits + a PR body (no HF calls)."""
    old_doc = json.loads(Path(vendored_lock).read_text())
    new_doc = json.loads(Path(new_lock).read_text())
    bindings_doc = yaml.safe_load(Path(bindings).read_text()) or {}

    try:
        plan = plan_promotion(old_doc, new_doc, bindings_doc)
    except PromoteError as exc:
        print_error(f"Promotion planning failed: {exc}")
        raise typer.Exit(2) from exc

    if plan.is_noop:
        console.print("[yellow]No catalog changes[/yellow] — nothing to promote.")
        Path(pr_body).write_text("")   # empty body signals the workflow to skip
        return

    Path(vendored_lock).write_text(Path(new_lock).read_text())  # refresh vendored lock verbatim
    _apply_pin_bump(list(pyproject or []), version)
    if plan.missing_bindings:
        _apply_stub_bindings(Path(bindings), plan.missing_bindings)
    Path(pr_body).write_text(render_pr_body(plan, version))
    Path(labels_out).write_text(",".join(pr_labels(plan)))

    console.print(
        f"[green]Planned[/green] {len(plan.alias_moves)} move(s), "
        f"{len(plan.missing_bindings)} stub(s), {len(plan.blocked)} blocked -> {pr_body}")
    if plan.blocked:
        raise typer.Exit(1)   # blocked: workflow still opens the PR, marks the check failed
