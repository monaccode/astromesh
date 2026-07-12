"""Plan HF Inference Endpoints for served Centinela bindings (pure, no I/O).

Given the foundry catalog lock (repo + revision sha per alias) and the operator's
bindings (which alias to serve, on what hardware), produce one DesiredEndpoint per
served binding, and diff a desired endpoint against the live one to decide create/
update/noop. All logic here is deterministic and unit-tested; the huggingface_hub
calls live in hf_endpoints.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from astromesh.centinela.reconcile import _SERVED_KINDS

_REAL_SHA = re.compile(r"^[0-9a-f]{7,40}$")


class EndpointPlanError(ValueError):
    """A binding cannot be planned into an endpoint."""


@dataclass(frozen=True)
class DesiredEndpoint:
    name: str
    model: str
    alias: str
    repository: str
    revision: str
    framework: str
    task: str
    type: str
    vendor: str
    region: str
    accelerator: str
    instance_type: str
    instance_size: str
    scale_to_zero: bool
    min_replica: int
    max_replica: int
    api_key_env: str
    ready: bool


@dataclass(frozen=True)
class EndpointAction:
    kind: str  # "create" | "update" | "noop"
    fields: dict  # changed fields for "update"; empty otherwise


def endpoint_name(model: str, alias: str) -> str:
    """Deterministic endpoint name, e.g. centinela-sentiment-prod."""
    return f"{model}-{alias}".lower()


def plan_endpoints(lock: dict, bindings: dict) -> list[DesiredEndpoint]:
    """One DesiredEndpoint per served binding; raises on an unservable binding."""
    models = {m["name"]: m for m in lock.get("models", [])}
    out: list[DesiredEndpoint] = []

    for b in bindings.get("spec", {}).get("bindings", []):
        name = b["model"]
        alias = b["alias"]

        model = models.get(name)
        if model is None:
            raise EndpointPlanError(f"binding references unknown model '{name}'")
        if model["kind"] not in _SERVED_KINDS:
            raise EndpointPlanError(
                f"{name} kind '{model['kind']}' is not served by Centinela endpoints"
            )

        version = model["aliases"].get(alias)
        if version is None:
            raise EndpointPlanError(f"{name}: alias '{alias}' not found in catalog")
        rev = model["revisions"][version]
        if rev["gate"] != "passed":
            raise EndpointPlanError(
                f"{name}:{version} has gate '{rev['gate']}', only 'passed' may be served"
            )

        serving = b.get("serving") or {}
        sha = rev["sha"]
        out.append(
            DesiredEndpoint(
                name=b.get("endpoint_name") or endpoint_name(name, alias),
                model=name,
                alias=alias,
                repository=model["hf_repo"],
                revision=sha,
                framework="pytorch",
                task="text-generation",
                type="protected",
                vendor=serving.get("vendor", "aws"),
                region=serving.get("region", "us-east-1"),
                accelerator=serving.get("accelerator", "gpu"),
                instance_type=serving.get("instance_type", "nvidia-a10g"),
                instance_size=serving.get("instance_size", "x1"),
                scale_to_zero=bool(serving.get("scale_to_zero", True)),
                min_replica=int(serving.get("min_replica", 0)),
                max_replica=int(serving.get("max_replica", 1)),
                api_key_env=serving.get("api_key_env", "HF_TOKEN"),
                ready=bool(_REAL_SHA.match(sha)),
            )
        )
    return out


def diff_endpoint(desired: DesiredEndpoint, actual: dict | None) -> EndpointAction:
    """Decide create/update/noop by comparing desired vs the live endpoint state."""
    if actual is None:
        return EndpointAction("create", {})
    fields: dict = {}
    if actual.get("revision") != desired.revision:
        fields["revision"] = desired.revision
    for f in ("accelerator", "instance_type", "instance_size"):
        if actual.get(f) != getattr(desired, f):
            fields[f] = getattr(desired, f)
    return EndpointAction("update", fields) if fields else EndpointAction("noop", {})
