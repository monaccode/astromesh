"""Compile Centinela deployment bindings + the foundry catalog lock into provider config.

Compile-only: this never touches HF infrastructure. Given the machine contract
(`catalog.lock.json`, produced by the astromesh-nebula foundry) and the operator's
`bindings.yaml`, produce the `type: centinela` entries for `config/providers.yaml`.
Output is deterministic (sorted) so it can be snapshot-tested.
"""

from __future__ import annotations

_SERVED_KINDS = {"classifier", "extractor"}


class ReconcileError(ValueError):
    """A binding cannot be reconciled against the catalog lock."""


def reconcile(lock: dict, bindings: dict) -> dict:
    """Map each binding to a Centinela provider entry, validating against the lock."""
    models = {m["name"]: m for m in lock.get("models", [])}
    out: dict[str, dict] = {}

    for b in bindings.get("spec", {}).get("bindings", []):
        name = b["model"]
        alias = b["alias"]

        model = models.get(name)
        if model is None:
            raise ReconcileError(f"binding references unknown model '{name}'")

        version = model["aliases"].get(alias)
        if version is None:
            raise ReconcileError(f"{name}: alias '{alias}' not found in catalog")

        rev = model["revisions"][version]
        if rev["gate"] != "passed":
            raise ReconcileError(
                f"{name}:{version} has gate '{rev['gate']}', only 'passed' may be served"
            )

        if model["kind"] not in _SERVED_KINDS:
            raise ReconcileError(
                f"{name} kind '{model['kind']}' is not served by the Centinela provider; "
                "instruct models route through hf_tgi"
            )

        out[name] = {
            "type": "centinela",
            "endpoint": b["endpoint"],
            "models": [name],
            "kind": model["kind"],
            "contract": model["contract"],
            "revision": version,
            "sha": rev["sha"],
        }

    return dict(sorted(out.items()))


def to_provider_config(providers: dict) -> dict:
    """Wrap reconciled provider entries in a ProviderConfig document."""
    return {
        "apiVersion": "astromesh/v1",
        "kind": "ProviderConfig",
        "metadata": {"name": "centinela-generated"},
        "spec": {"providers": providers},
    }
