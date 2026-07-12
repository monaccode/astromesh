"""astromeshctl centinela — reconcile Centinela bindings into provider config."""

import json
import os
from importlib.resources import files
from pathlib import Path
from typing import Optional

import typer
import yaml

from astromesh.centinela import hf_endpoints
from astromesh.centinela.endpoints import EndpointPlanError, diff_endpoint, plan_endpoints
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


@app.command("apply-endpoints")
def apply_endpoints_command(
    bindings: str = typer.Option(
        "./config/centinela/bindings.yaml", "--bindings", help="Path to bindings.yaml"),
    out: str = typer.Option(
        "./config/providers.centinela.yaml", "--out", help="Output ProviderConfig path"),
    namespace: str = typer.Option(None, "--namespace", help="HF namespace/org (default $HF_ORG)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan only; no HF mutation"),
    wait_timeout: int = typer.Option(1800, "--wait-timeout", help="Seconds to await running"),
) -> None:
    """Provision/update HF Inference Endpoints for served bindings; write provider config."""
    ns = namespace or os.environ.get("HF_ORG")
    token = os.environ.get("HF_TOKEN")
    lock = _load_lock()
    models = {m["name"]: m for m in lock.get("models", [])}
    bindings_doc = yaml.safe_load(Path(bindings).read_text()) or {}

    try:
        desired_list = plan_endpoints(lock, bindings_doc)
    except EndpointPlanError as exc:
        print_error(f"Endpoint planning failed: {exc}")
        raise typer.Exit(2) from exc

    providers: dict = {}
    for d in desired_list:
        if not d.ready:
            console.print(f"[yellow]skip[/yellow] {d.name}: model not published (placeholder sha)")
            continue
        actual = hf_endpoints.get_endpoint(d.name, namespace=ns, token=token)
        action = diff_endpoint(d, actual)
        if dry_run:
            console.print(f"[cyan]plan[/cyan] {d.name}: {action.kind} {action.fields or ''}")
            continue
        if action.kind == "create":
            ep = hf_endpoints.create_endpoint(d, namespace=ns, token=token)
            url = hf_endpoints.wait_url(ep, timeout=wait_timeout)
        elif action.kind == "update":
            ep = hf_endpoints.update_endpoint(d.name, action.fields, namespace=ns, token=token)
            url = hf_endpoints.wait_url(ep, timeout=wait_timeout)
        else:
            url = (actual or {}).get("url") or hf_endpoints.resolve_url(
                d.name, namespace=ns, token=token)
        model = models[d.model]
        providers[d.model] = {
            "type": "centinela",
            "endpoint": url,
            "endpoint_name": d.name,
            "api_key_env": d.api_key_env,
            "models": [d.model],
            "kind": model["kind"],
            "contract": model["contract"],
            "revision": d.alias,
            "sha": d.revision,
        }

    if dry_run:
        console.print("[green]dry-run complete[/green] — no endpoints changed, no file written")
        return

    doc = to_provider_config(dict(sorted(providers.items())))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(yaml.safe_dump(doc, sort_keys=True, allow_unicode=True))
    console.print(f"[green]Applied[/green] {len(providers)} endpoint(s) -> {out}")
