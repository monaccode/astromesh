# Centinela Live Endpoint Provisioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the compile-only Centinela reconciler into one that provisions HF Inference Endpoints and wires the live URL + serving auth into the runtime provider.

**Architecture:** A pure planner (`plan_endpoints`/`diff_endpoint`) computes desired endpoints from the lock + bindings; a thin mockable `huggingface_hub` wrapper does the create/update/get; an `apply-endpoints` CLI orchestrates them and writes `providers.centinela.yaml`; a merge-triggered workflow applies and commits the URL back; the provider sends a Bearer token and can resolve its URL from the endpoint name.

**Tech Stack:** Python 3.11+/3.12+, typer, PyYAML, httpx, `huggingface_hub>=0.24`, respx (tests); GitHub Actions.

## Global Constraints

- **Repo & branch:** all tasks in **astromesh** on branch `feat/centinela-live-endpoints` off `develop`.
- **Python:** 3.11+ (astromesh core targets 3.12+); `ruff` line length 100.
- **Zero live HF calls in tests** — `huggingface_hub` is fully mocked/monkeypatched. The only new runtime dep is `huggingface_hub>=0.24`, added to astromesh's `centinela` extra (already present transitively via `astromesh-nebula`, but declare it directly since astromesh now imports it).
- **Reuse, don't redefine:** import `_SERVED_KINDS` from `astromesh/centinela/reconcile.py`; reuse `to_provider_config` from the same module.
- **Real-SHA gate:** a revision is "published" iff its `sha` matches `^[0-9a-f]{7,40}$`. A binding whose target sha is a placeholder is planned `ready=False` and skipped by apply (today's lock is all placeholders → apply is a safe no-op).
- **Endpoint type** is `"protected"`; **framework** `"pytorch"`; **task** `"text-generation"`; endpoint **name** defaults to `f"{model}-{alias}".lower()`.
- **Calling a typer command as a function** (workflow + tests) requires passing **every** parameter explicitly — an omitted parameter's default is a `typer.OptionInfo` object, not the value.
- **Commits:** Conventional Commits; every commit body ends with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Test fixtures** are plain dict literals matching `tests/test_centinela_reconcile.py` (lock shape: model `{name, kind, task, vertical, hf_repo, contract, aliases:{alias:rev}, revisions:{rev:{version, sha, gate, eval}}}`).

---

### Task 1: Pure endpoint planner (`endpoints.py`)

**Files:**
- Create: `astromesh/centinela/endpoints.py`
- Test: `tests/test_centinela_endpoints.py`

**Interfaces:**
- Consumes: `astromesh.centinela.reconcile._SERVED_KINDS` (`set[str]`).
- Produces (used by Tasks 2, 3): `EndpointPlanError`, frozen dataclasses `DesiredEndpoint` and `EndpointAction(kind, fields)`, `endpoint_name(model, alias) -> str`, `plan_endpoints(lock, bindings) -> list[DesiredEndpoint]`, `diff_endpoint(desired, actual) -> EndpointAction`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_centinela_endpoints.py
import pytest

from astromesh.centinela.endpoints import (
    EndpointAction,
    EndpointPlanError,
    diff_endpoint,
    endpoint_name,
    plan_endpoints,
)

REAL_SHA = "a" * 40


def _rev(rev, sha=REAL_SHA, gate="passed"):
    return {"version": rev, "sha": sha, "gate": gate,
            "eval": {"macro_f1": 0.9, "invalid_rate": 0.01}}


def _model(name="centinela-sentiment", kind="classifier", aliases=None, revisions=None):
    return {"name": name, "kind": kind, "task": "text-classification", "vertical": "finanzas",
            "hf_repo": "astromesh/Centinela-Qwen3-4B",
            "contract": {"labels": ["positivo", "neutral", "negativo"]},
            "aliases": aliases if aliases is not None else {"prod": "v0.1"},
            "revisions": revisions if revisions is not None else {"v0.1": _rev("v0.1")}}


def _lock(models):
    return {"schema_version": "1", "models": models}


def _bindings(entries):
    return {"apiVersion": "astromesh/v1", "kind": "CentinelaBindings",
            "metadata": {"name": "default"}, "spec": {"bindings": entries}}


def _binding(alias="prod", serving=None):
    b = {"model": "centinela-sentiment", "alias": alias}
    if serving is not None:
        b["serving"] = serving
    return b


def test_endpoint_name_is_deterministic():
    assert endpoint_name("centinela-sentiment", "prod") == "centinela-sentiment-prod"


def test_plan_served_binding_real_sha_is_ready():
    plan = plan_endpoints(_lock([_model()]), _bindings([_binding(serving={
        "vendor": "aws", "region": "us-east-1", "accelerator": "gpu",
        "instance_type": "nvidia-a10g", "instance_size": "x1"})]))
    assert len(plan) == 1
    d = plan[0]
    assert d.name == "centinela-sentiment-prod"
    assert d.repository == "astromesh/Centinela-Qwen3-4B"
    assert d.revision == REAL_SHA
    assert d.instance_type == "nvidia-a10g"
    assert d.type == "protected"
    assert d.ready is True


def test_plan_placeholder_sha_is_not_ready():
    m = _model(revisions={"v0.1": _rev("v0.1", sha="REPLACE_WITH_REAL_HF_REVISION_SHA")})
    plan = plan_endpoints(_lock([m]), _bindings([_binding()]))
    assert plan[0].ready is False


def test_plan_defaults_serving_when_absent():
    plan = plan_endpoints(_lock([_model()]), _bindings([_binding(serving=None)]))
    d = plan[0]
    assert d.vendor == "aws" and d.scale_to_zero is True and d.api_key_env == "HF_TOKEN"


def test_plan_unknown_model_raises():
    with pytest.raises(EndpointPlanError):
        plan_endpoints(_lock([]), _bindings([_binding()]))


def test_plan_non_served_kind_raises():
    m = _model(name="centinela-chat", kind="instruct", aliases={"prod": "v1"},
               revisions={"v1": _rev("v1")})
    with pytest.raises(EndpointPlanError):
        plan_endpoints(_lock([m]), _bindings([{"model": "centinela-chat", "alias": "prod"}]))


def test_plan_gate_not_passed_raises():
    m = _model(revisions={"v0.1": _rev("v0.1", gate="pending")})
    with pytest.raises(EndpointPlanError):
        plan_endpoints(_lock([m]), _bindings([_binding()]))


def test_diff_create_when_absent():
    d = plan_endpoints(_lock([_model()]), _bindings([_binding()]))[0]
    assert diff_endpoint(d, None) == EndpointAction("create", {})


def test_diff_update_on_revision_change():
    d = plan_endpoints(_lock([_model()]), _bindings([_binding()]))[0]
    actual = {"revision": "b" * 40, "accelerator": "gpu",
              "instance_type": "nvidia-a10g", "instance_size": "x1"}
    action = diff_endpoint(d, actual)
    assert action.kind == "update"
    assert action.fields == {"revision": REAL_SHA}


def test_diff_noop_when_identical():
    d = plan_endpoints(_lock([_model()]), _bindings([_binding(serving={
        "instance_type": "nvidia-a10g", "instance_size": "x1", "accelerator": "gpu"})]))[0]
    actual = {"revision": REAL_SHA, "accelerator": "gpu",
              "instance_type": "nvidia-a10g", "instance_size": "x1"}
    assert diff_endpoint(d, actual) == EndpointAction("noop", {})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_centinela_endpoints.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'astromesh.centinela.endpoints'`

- [ ] **Step 3: Write the planner**

```python
# astromesh/centinela/endpoints.py
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
    kind: str          # "create" | "update" | "noop"
    fields: dict       # changed fields for "update"; empty otherwise


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
                f"{name} kind '{model['kind']}' is not served by Centinela endpoints")

        version = model["aliases"].get(alias)
        if version is None:
            raise EndpointPlanError(f"{name}: alias '{alias}' not found in catalog")
        rev = model["revisions"][version]
        if rev["gate"] != "passed":
            raise EndpointPlanError(
                f"{name}:{version} has gate '{rev['gate']}', only 'passed' may be served")

        serving = b.get("serving") or {}
        sha = rev["sha"]
        out.append(DesiredEndpoint(
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
        ))
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_centinela_endpoints.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Lint**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run ruff check astromesh/centinela/endpoints.py tests/test_centinela_endpoints.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
git add astromesh/centinela/endpoints.py tests/test_centinela_endpoints.py
git commit -m "$(cat <<'MSG'
feat(centinela): pure endpoint planner

plan_endpoints() maps served bindings + the catalog lock to DesiredEndpoint specs
(marking placeholder-sha bindings not-ready), and diff_endpoint() decides create/update/
noop against the live endpoint state. Reuses the reconciler's serve rules.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
)"
```

---

### Task 2: `huggingface_hub` wrapper (`hf_endpoints.py`)

**Files:**
- Create: `astromesh/centinela/hf_endpoints.py`
- Test: `tests/test_centinela_hf_endpoints.py`
- Modify: `pyproject.toml` (add `huggingface_hub>=0.24` to the `centinela` extra)

**Interfaces:**
- Consumes: `DesiredEndpoint` from Task 1.
- Produces (used by Tasks 3, 4): `get_endpoint(name, *, namespace, token) -> dict | None`, `create_endpoint(desired, *, namespace, token) -> object`, `update_endpoint(name, fields, *, namespace, token) -> object`, `wait_url(endpoint, *, timeout) -> str`, `resolve_url(name, *, namespace, token) -> str | None`.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, change the `centinela` extra line:

```toml
centinela = ["astromesh-nebula>=0.1.0", "huggingface_hub>=0.24"]
```

Run: `cd /Users/fulfaro/monaccode/astromesh && uv sync --extra dev --extra centinela`
Expected: resolves; `python -c "import huggingface_hub"` works in the env.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_centinela_hf_endpoints.py
import huggingface_hub

from astromesh.centinela import hf_endpoints
from astromesh.centinela.endpoints import plan_endpoints


class _FakeEndpoint:
    def __init__(self, url="https://ep.aws.endpoints.huggingface.cloud"):
        self.name = "centinela-sentiment-prod"
        self.repository = "astromesh/Centinela-Qwen3-4B"
        self.status = "running"
        self.url = url
        self.raw = {"model": {"revision": "a" * 40},
                    "compute": {"accelerator": "gpu", "instanceType": "nvidia-a10g",
                                "instanceSize": "x1"}}

    def wait(self, timeout=None):
        return self


def _desired():
    lock = {"schema_version": "1", "models": [{
        "name": "centinela-sentiment", "kind": "classifier", "task": "text-classification",
        "vertical": "finanzas", "hf_repo": "astromesh/Centinela-Qwen3-4B",
        "contract": {"labels": ["positivo"]}, "aliases": {"prod": "v0.1"},
        "revisions": {"v0.1": {"version": "v0.1", "sha": "a" * 40, "gate": "passed",
                               "eval": {"macro_f1": 0.9, "invalid_rate": 0.01}}}}]}
    bindings = {"spec": {"bindings": [{"model": "centinela-sentiment", "alias": "prod"}]}}
    return plan_endpoints(lock, bindings)[0]


def test_get_endpoint_normalizes(monkeypatch):
    monkeypatch.setattr(huggingface_hub, "get_inference_endpoint",
                        lambda *a, **k: _FakeEndpoint())
    got = hf_endpoints.get_endpoint("centinela-sentiment-prod", namespace="org", token="t")
    assert got["revision"] == "a" * 40
    assert got["instance_type"] == "nvidia-a10g"
    assert got["url"].startswith("https://")


def test_get_endpoint_returns_none_on_404(monkeypatch):
    import httpx
    from huggingface_hub.utils import HfHubHTTPError

    def _raise(*a, **k):
        raise HfHubHTTPError("not found", response=httpx.Response(404))

    monkeypatch.setattr(huggingface_hub, "get_inference_endpoint", _raise)
    assert hf_endpoints.get_endpoint("missing", namespace="org", token="t") is None


def test_create_endpoint_passes_mapped_kwargs(monkeypatch):
    captured = {}

    def _create(name, **kwargs):
        captured["name"] = name
        captured.update(kwargs)
        return _FakeEndpoint()

    monkeypatch.setattr(huggingface_hub, "create_inference_endpoint", _create)
    hf_endpoints.create_endpoint(_desired(), namespace="org", token="t")
    assert captured["name"] == "centinela-sentiment-prod"
    assert captured["repository"] == "astromesh/Centinela-Qwen3-4B"
    assert captured["revision"] == "a" * 40
    assert captured["type"] == "protected"
    assert captured["instance_type"] == "nvidia-a10g"


def test_wait_url_returns_url():
    assert hf_endpoints.wait_url(_FakeEndpoint(url="https://x"), timeout=5) == "https://x"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_centinela_hf_endpoints.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'astromesh.centinela.hf_endpoints'`

- [ ] **Step 4: Write the wrapper**

```python
# astromesh/centinela/hf_endpoints.py
"""Thin, mockable wrapper over huggingface_hub Inference Endpoint APIs.

This is the ONLY module that touches HF over the network. huggingface_hub is imported
lazily inside each function so importing this module (and the provider that falls back to
it) never requires the package at import time. Tests monkeypatch huggingface_hub.

Note: the field mapping in _normalize() reflects the InferenceEndpoint `.raw` payload
(model.revision, compute.accelerator/instanceType/instanceSize) and should be verified
against the live API when the first real endpoint is created.
"""

from __future__ import annotations

from typing import Any

from astromesh.centinela.endpoints import DesiredEndpoint


def _normalize(ep: Any) -> dict:
    raw = getattr(ep, "raw", None) or {}
    compute = raw.get("compute") or {}
    model = raw.get("model") or {}
    return {
        "name": getattr(ep, "name", None),
        "repository": getattr(ep, "repository", None),
        "revision": model.get("revision"),
        "accelerator": compute.get("accelerator"),
        "instance_type": compute.get("instanceType"),
        "instance_size": compute.get("instanceSize"),
        "status": getattr(ep, "status", None),
        "url": getattr(ep, "url", None),
    }


def get_endpoint(name: str, *, namespace: str | None, token: str | None) -> dict | None:
    """Return normalized live state for an endpoint, or None if it does not exist."""
    from huggingface_hub import get_inference_endpoint
    from huggingface_hub.utils import HfHubHTTPError

    try:
        ep = get_inference_endpoint(name, namespace=namespace, token=token)
    except HfHubHTTPError as exc:
        resp = getattr(exc, "response", None)
        if resp is not None and resp.status_code == 404:
            return None
        raise
    return _normalize(ep)


def create_endpoint(desired: DesiredEndpoint, *, namespace: str | None, token: str | None):
    """Create the endpoint described by `desired`."""
    from huggingface_hub import create_inference_endpoint

    return create_inference_endpoint(
        desired.name,
        repository=desired.repository,
        revision=desired.revision,
        framework=desired.framework,
        task=desired.task,
        accelerator=desired.accelerator,
        vendor=desired.vendor,
        region=desired.region,
        type=desired.type,
        instance_size=desired.instance_size,
        instance_type=desired.instance_type,
        namespace=namespace,
        token=token,
        min_replica=desired.min_replica,
        max_replica=desired.max_replica,
        scale_to_zero_timeout=900 if desired.scale_to_zero else None,
    )


def update_endpoint(name: str, fields: dict, *, namespace: str | None, token: str | None):
    """Update an existing endpoint's revision and/or hardware in place."""
    from huggingface_hub import get_inference_endpoint

    ep = get_inference_endpoint(name, namespace=namespace, token=token)
    return ep.update(**fields)


def wait_url(endpoint: Any, *, timeout: int) -> str:
    """Block until the endpoint is running and return its URL."""
    return endpoint.wait(timeout=timeout).url


def resolve_url(name: str, *, namespace: str | None, token: str | None) -> str | None:
    """Best-effort resolve a live URL from an endpoint name (provider fallback)."""
    from huggingface_hub import get_inference_endpoint
    from huggingface_hub.utils import HfHubHTTPError

    try:
        return get_inference_endpoint(name, namespace=namespace, token=token).url
    except HfHubHTTPError:
        return None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_centinela_hf_endpoints.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Lint & commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
uv run ruff check astromesh/centinela/hf_endpoints.py tests/test_centinela_hf_endpoints.py
git add astromesh/centinela/hf_endpoints.py tests/test_centinela_hf_endpoints.py pyproject.toml
git commit -m "$(cat <<'MSG'
feat(centinela): mockable huggingface_hub endpoint wrapper

Isolates get/create/update/wait/resolve over huggingface_hub Inference Endpoints (lazy
import, normalized state) so the planner and provider stay testable without live HF.
Adds huggingface_hub to the centinela extra.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
)"
```

---

### Task 3: `apply-endpoints` CLI

**Files:**
- Modify: `astromesh-node/src/astromesh_node/cli/commands/centinela.py` (add command + imports)
- Modify: `astromesh-node/tests/test_centinela_cli.py` (append tests)

**Interfaces:**
- Consumes: `plan_endpoints`, `diff_endpoint`, `EndpointPlanError` (Task 1); `hf_endpoints` module (Task 2); existing `_load_lock`, `to_provider_config`.
- Produces: CLI command `apply-endpoints(bindings, out, namespace, dry_run, wait_timeout)`. Exit 2 on plan error; writes `providers.centinela.yaml`.

- [ ] **Step 1: Write the failing tests**

Add the new imports to the top import block of `astromesh-node/tests/test_centinela_cli.py` (alongside the existing `import json`, `import pytest`, `import typer`, and the `astromesh.centinela.promote` import):

```python
from astromesh.centinela import hf_endpoints as _hf
```

Append these tests:

```python
def _sentiment_lock(sha="a" * 40, gate="passed"):
    return {"schema_version": "1", "models": [{
        "name": "centinela-sentiment", "kind": "classifier", "task": "text-classification",
        "vertical": "finanzas", "hf_repo": "astromesh/Centinela-Qwen3-4B",
        "contract": {"labels": ["positivo", "neutral", "negativo"]},
        "aliases": {"prod": "v0.1"},
        "revisions": {"v0.1": {"version": "v0.1", "sha": sha, "gate": gate,
                               "eval": {"macro_f1": 0.9, "invalid_rate": 0.01}}}}]}


def _serving_bindings():
    return {"apiVersion": "astromesh/v1", "kind": "CentinelaBindings",
            "metadata": {"name": "default"},
            "spec": {"bindings": [{"model": "centinela-sentiment", "alias": "prod",
                                   "serving": {"instance_type": "nvidia-a10g",
                                               "instance_size": "x1"}}]}}


class _FakeEp:
    url = "https://ep.aws.endpoints.huggingface.cloud"

    def wait(self, timeout=None):
        return self


def test_apply_endpoints_create_writes_provider_config(tmp_path, monkeypatch):
    monkeypatch.setattr(centinela, "_load_lock", lambda: _sentiment_lock())
    monkeypatch.setattr(_hf, "get_endpoint", lambda *a, **k: None)  # absent -> create
    created = {}
    monkeypatch.setattr(_hf, "create_endpoint",
                        lambda d, **k: created.setdefault("name", d.name) or _FakeEp())
    monkeypatch.setattr(_hf, "wait_url", lambda ep, **k: ep.url)

    bindings_path = tmp_path / "bindings.yaml"
    bindings_path.write_text(yaml.safe_dump(_serving_bindings()))
    out_path = tmp_path / "providers.centinela.yaml"

    centinela.apply_endpoints_command(
        bindings=str(bindings_path), out=str(out_path), namespace="org",
        dry_run=False, wait_timeout=5)

    assert created["name"] == "centinela-sentiment-prod"
    doc = yaml.safe_load(out_path.read_text())
    entry = doc["spec"]["providers"]["centinela-sentiment"]
    assert entry["endpoint"] == "https://ep.aws.endpoints.huggingface.cloud"
    assert entry["endpoint_name"] == "centinela-sentiment-prod"
    assert entry["api_key_env"] == "HF_TOKEN"


def test_apply_endpoints_dry_run_makes_no_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(centinela, "_load_lock", lambda: _sentiment_lock())
    monkeypatch.setattr(_hf, "get_endpoint", lambda *a, **k: None)

    def _boom(*a, **k):
        raise AssertionError("must not mutate in dry-run")

    monkeypatch.setattr(_hf, "create_endpoint", _boom)
    monkeypatch.setattr(_hf, "update_endpoint", _boom)

    bindings_path = tmp_path / "bindings.yaml"
    bindings_path.write_text(yaml.safe_dump(_serving_bindings()))
    out_path = tmp_path / "providers.centinela.yaml"

    centinela.apply_endpoints_command(
        bindings=str(bindings_path), out=str(out_path), namespace="org",
        dry_run=True, wait_timeout=5)

    assert not out_path.exists()


def test_apply_endpoints_skips_not_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(centinela, "_load_lock",
                        lambda: _sentiment_lock(sha="REPLACE_WITH_REAL_HF_REVISION_SHA"))

    def _boom(*a, **k):
        raise AssertionError("must not touch HF for a not-ready binding")

    monkeypatch.setattr(_hf, "get_endpoint", _boom)
    bindings_path = tmp_path / "bindings.yaml"
    bindings_path.write_text(yaml.safe_dump(_serving_bindings()))
    out_path = tmp_path / "providers.centinela.yaml"

    centinela.apply_endpoints_command(
        bindings=str(bindings_path), out=str(out_path), namespace="org",
        dry_run=False, wait_timeout=5)

    doc = yaml.safe_load(out_path.read_text())
    assert doc["spec"]["providers"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fulfaro/monaccode/astromesh/astromesh-node && uv run pytest tests/test_centinela_cli.py -k apply_endpoints -v`
Expected: FAIL — `AttributeError: ... has no attribute 'apply_endpoints_command'`

- [ ] **Step 3: Add the command**

Add to the top import block of `centinela.py`:

```python
import os

from astromesh.centinela import hf_endpoints
from astromesh.centinela.endpoints import EndpointPlanError, diff_endpoint, plan_endpoints
```

Append the command:

```python
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
```

Note: `to_provider_config` is already imported in this file (used by `reconcile_command`); confirm the existing import line includes it and add it if missing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fulfaro/monaccode/astromesh/astromesh-node && uv run pytest tests/test_centinela_cli.py -v`
Expected: PASS (existing tests + 3 new apply_endpoints tests)

- [ ] **Step 5: Lint & commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
uv run ruff check astromesh-node/src/astromesh_node/cli/commands/centinela.py astromesh-node/tests/test_centinela_cli.py
git add astromesh-node/src/astromesh_node/cli/commands/centinela.py astromesh-node/tests/test_centinela_cli.py
git commit -m "$(cat <<'MSG'
feat(centinela): apply-endpoints CLI

astromeshctl centinela apply-endpoints plans + provisions HF Inference Endpoints for
served bindings (create/update/noop, skips not-ready placeholders), waits for each URL,
and writes providers.centinela.yaml with endpoint_name + api_key_env. --dry-run plans
without mutating.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
)"
```

---

### Task 4: Provider serving auth + endpoint_name fallback + engine threading

**Files:**
- Modify: `astromesh/providers/centinela.py` (`_CentinelaEndpointClient` auth + resolve)
- Modify: `astromesh/runtime/engine.py` (thread endpoint_name/api_key/api_key_env at lines 148-160)
- Modify: `tests/test_centinela_provider.py` (append tests)

**Interfaces:**
- Consumes: `hf_endpoints.resolve_url` (Task 2).
- Produces: a `_CentinelaEndpointClient` that sends `Authorization: Bearer <token>` when a token is configured and resolves its URL from `endpoint_name` when `endpoint` is absent.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_centinela_provider.py
import os


@respx.mock
async def test_classify_sends_bearer_auth():
    route = respx.post("http://ep.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_chat_response("positivo")))
    client = _CentinelaEndpointClient(
        {"endpoint": "http://ep.test", "contract": CONTRACT, "api_key": "secret-token"})
    await client.classify("subieron las ganancias")
    assert route.calls.last.request.headers["authorization"] == "Bearer secret-token"


@respx.mock
async def test_api_key_env_is_read_from_environment(monkeypatch):
    monkeypatch.setenv("CENTINELA_TOKEN", "env-token")
    route = respx.post("http://ep.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_chat_response("neutral")))
    client = _CentinelaEndpointClient(
        {"endpoint": "http://ep.test", "contract": CONTRACT, "api_key_env": "CENTINELA_TOKEN"})
    await client.classify("informe estable")
    assert route.calls.last.request.headers["authorization"] == "Bearer env-token"


@respx.mock
async def test_endpoint_resolved_from_name_when_url_absent(monkeypatch):
    from astromesh.centinela import hf_endpoints
    monkeypatch.setattr(hf_endpoints, "resolve_url", lambda *a, **k: "http://resolved.test")
    respx.post("http://resolved.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_chat_response("positivo")))
    client = _CentinelaEndpointClient(
        {"endpoint_name": "centinela-sentiment-prod", "contract": CONTRACT})
    result = await client.classify("gran resultado")
    assert result.label == "positivo"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_centinela_provider.py -k "bearer or api_key_env or resolved" -v`
Expected: FAIL — the request carries no `authorization` header / URL not resolved.

- [ ] **Step 3: Add auth + fallback to the client**

Add `import os` to the top of `astromesh/providers/centinela.py` (with the existing imports).

Replace the `_CentinelaEndpointClient.__init__` endpoint/field setup and `_get_client` with:

```python
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.endpoint: str = (config.get("endpoint") or "").rstrip("/")
        self.endpoint_name: str | None = config.get("endpoint_name")
        api_key_env = config.get("api_key_env")
        self.api_key: str | None = config.get("api_key") or (
            os.environ.get(api_key_env) if api_key_env else None)
        self.model: str = config.get("model", "centinela")
        self.timeout: float = float(config.get("timeout", 30.0))
        contract = config.get("contract") or {}
        self.labels: list[str] = list(contract.get("labels", []))
        self.invalid_policy: str = config.get("invalid_policy", "mark")
        self.max_retries: int = int(config.get("max_retries", 1))
        self._client: httpx.AsyncClient | None = None

    def _resolve_endpoint(self) -> str:
        if self.endpoint:
            return self.endpoint
        if self.endpoint_name:
            from astromesh.centinela import hf_endpoints

            url = hf_endpoints.resolve_url(
                self.endpoint_name, namespace=os.environ.get("HF_ORG"), token=self.api_key)
            if url:
                return url.rstrip("/")
        return "http://localhost:8080"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            base = self._resolve_endpoint()
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None
            self._client = httpx.AsyncClient(base_url=base, timeout=self.timeout, headers=headers)
        return self._client
```

- [ ] **Step 4: Thread the new fields in engine.py**

Replace the centinela block in `astromesh/runtime/engine.py` (lines ~148-160) with:

```python
    if source == "centinela":
        from astromesh.providers.centinela import CentinelaProvider

        return CentinelaProvider(
            config={
                "endpoint": block.get("endpoint"),
                "endpoint_name": block.get("endpoint_name"),
                "api_key": block.get("api_key"),
                "api_key_env": block.get("api_key_env"),
                "model": model or "centinela",
                "contract": block.get("contract") or {},
                "invalid_policy": block.get("invalid_policy", "mark"),
                "max_retries": int(block.get("max_retries", 1)),
            }
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_centinela_provider.py tests/test_centinela_wiring.py -v`
Expected: PASS. (If `test_centinela_wiring.py` asserted the exact old config dict for the centinela block, update that assertion to match the new threaded keys — the endpoint is still threaded, so behavior is unchanged when only `endpoint` is set.)

- [ ] **Step 6: Lint & commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
uv run ruff check astromesh/providers/centinela.py astromesh/runtime/engine.py tests/test_centinela_provider.py
git add astromesh/providers/centinela.py astromesh/runtime/engine.py tests/test_centinela_provider.py
git commit -m "$(cat <<'MSG'
feat(centinela): serving auth + endpoint-name URL fallback

The provider now sends Authorization: Bearer from api_key/api_key_env and, when no
endpoint URL is configured, resolves one from endpoint_name via the hf wrapper. engine
threads endpoint_name/api_key/api_key_env into the routed provider.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
)"
```

---

### Task 5: Bindings serving migration + reconcile tolerance

**Files:**
- Modify: `config/centinela/bindings.yaml` (serving block replaces endpoint)
- Modify: `astromesh/centinela/reconcile.py:49` (`b["endpoint"]` → `b.get("endpoint")`)
- Modify: `tests/test_centinela_reconcile.py` (append a tolerance test)

**Interfaces:**
- Produces: a seed `bindings.yaml` in the new `serving` shape; `reconcile` no longer requires `endpoint`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_centinela_reconcile.py
def test_reconcile_tolerates_binding_without_endpoint():
    lock = _lock()  # existing helper in this file
    bindings = {"apiVersion": "astromesh/v1", "kind": "CentinelaBindings",
                "metadata": {"name": "default"},
                "spec": {"bindings": [{"model": "centinela-sentiment", "alias": "prod",
                                       "serving": {"instance_type": "nvidia-a10g"}}]}}
    out = reconcile(lock, bindings)
    assert out["centinela-sentiment"]["type"] == "centinela"
    assert out["centinela-sentiment"]["endpoint"] is None
```

(Verify the existing `_lock()` helper in this file maps `centinela-sentiment` prod → a passed revision; it does. If its prod revision differs, adjust the alias/model in the test to a served, gate-passed entry.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_centinela_reconcile.py -k tolerates -v`
Expected: FAIL — `KeyError: 'endpoint'`

- [ ] **Step 3: Make reconcile tolerate a missing endpoint**

In `astromesh/centinela/reconcile.py`, change line 49 from:

```python
            "endpoint": b["endpoint"],
```

to:

```python
            "endpoint": b.get("endpoint"),
```

- [ ] **Step 4: Migrate the seed bindings.yaml**

Replace `config/centinela/bindings.yaml` with:

```yaml
apiVersion: astromesh/v1
kind: CentinelaBindings
metadata:
  name: default
spec:
  bindings:
    - model: centinela-sentiment
      alias: prod
      serving:
        vendor: aws            # aws | azure | gcp
        region: us-east-1
        accelerator: gpu
        instance_type: nvidia-a10g
        instance_size: x1
        scale_to_zero: true    # cost lever; adds cold-start latency
        min_replica: 0
        max_replica: 1
      # endpoint_name: optional override; default = "<model>-<alias>"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_centinela_reconcile.py -v` and
`cd /Users/fulfaro/monaccode/astromesh/astromesh-node && uv run pytest tests/test_centinela_cli.py -v`
Expected: PASS — including the reconcile end-to-end test (it only asserts the provider `type`, so the seed change is safe) and the new tolerance test.

- [ ] **Step 6: Lint & commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
uv run ruff check astromesh/centinela/reconcile.py tests/test_centinela_reconcile.py
git add config/centinela/bindings.yaml astromesh/centinela/reconcile.py tests/test_centinela_reconcile.py
git commit -m "$(cat <<'MSG'
feat(centinela): bindings carry a serving block; reconcile tolerates no endpoint

The seed bindings move from a hand-set endpoint URL to a declarative serving block
(hardware/scaling) consumed by apply-endpoints; the endpoint URL is now an output.
reconcile no longer requires the endpoint key.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
)"
```

---

### Task 6: Apply workflow — `centinela-endpoints.yml`

**Files:**
- Create: `.github/workflows/centinela-endpoints.yml`
- Test: `tests/test_workflow_yaml.py` (append — the file exists from sub-project 4)

**Interfaces:**
- Consumes: `apply_endpoints_command` (Task 3); `secrets.HF_TOKEN`, `vars.HF_ORG`.
- Produces: on merge touching `bindings.yaml`, applies endpoints and commits `providers.centinela.yaml` back.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_workflow_yaml.py
def test_centinela_endpoints_workflow_parses():
    wf = yaml.safe_load((_ROOT / ".github/workflows/centinela-endpoints.yml").read_text())
    on = wf.get("on", wf.get(True))
    assert "config/centinela/bindings.yaml" in on["push"]["paths"]
    steps = wf["jobs"]["apply"]["steps"]
    assert any("apply_endpoints_command" in str(s.get("run", "")) for s in steps)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_workflow_yaml.py -k endpoints -v`
Expected: FAIL — `FileNotFoundError`

- [ ] **Step 3: Write the workflow**

```yaml
# .github/workflows/centinela-endpoints.yml
name: centinela-endpoints
on:
  push:
    branches: [develop, main]
    paths: [config/centinela/bindings.yaml]

permissions:
  contents: write

jobs:
  apply:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - uses: astral-sh/setup-uv@v7

      - name: Apply endpoints
        working-directory: astromesh-node
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
          HF_ORG: ${{ vars.HF_ORG }}
        run: |
          uv sync --extra test
          uv run python -c '
          from astromesh_node.cli.commands.centinela import apply_endpoints_command
          apply_endpoints_command(
              bindings="../config/centinela/bindings.yaml",
              out="../config/providers.centinela.yaml",
              namespace=None,
              dry_run=False,
              wait_timeout=1800,
          )
          '

      - name: Commit generated provider config
        run: |
          if [ -f config/providers.centinela.yaml ] && ! git diff --quiet -- config/providers.centinela.yaml; then
            git config user.name "centinela-bot"
            git config user.email "bot@astromesh.local"
            git add config/providers.centinela.yaml
            git commit -m "chore(centinela): sync live endpoint URLs [skip ci]

          Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
            git push
          fi
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_workflow_yaml.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
git add .github/workflows/centinela-endpoints.yml tests/test_workflow_yaml.py
git commit -m "$(cat <<'MSG'
feat(centinela): apply-endpoints workflow on bindings merge

On push to develop/main touching config/centinela/bindings.yaml, provision endpoints
(apply_endpoints_command from the astromesh-node env) and commit the regenerated
providers.centinela.yaml back with [skip ci]. Real apply gated by the bindings PR.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
)"
```

---

## Post-implementation (controller, after all tasks)

- Full suites green in both projects: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest -q`; `cd astromesh-node && uv run pytest -q`. Ruff clean.
- **Ops follow-up (not code; note in PR):** set repo variable `HF_ORG` and secret `HF_TOKEN` (with Inference-Endpoint management scope) on astromesh; the first real apply only happens once a model trains (real sha). Verify `hf_endpoints._normalize` against the live `InferenceEndpoint.raw` payload at that point.
- Final whole-branch review, then `superpowers:finishing-a-development-branch`. Pushing is outward-facing — confirm with the user first.

## Self-review notes

- **Spec coverage:** planner (§2.1)→T1; wrapper (§2.2)→T2; CLI (§2.3)→T3; workflow (§2.4)→T6; provider auth+fallback (§2.5)→T4; bindings data model (§3)→T5. All covered.
- **Type consistency:** `DesiredEndpoint`/`EndpointAction`/`plan_endpoints`/`diff_endpoint`/`endpoint_name` (T1) used identically in T2/T3; `hf_endpoints.{get,create,update,wait_url,resolve_url}_endpoint` names consistent T2↔T3↔T4; provider config keys `endpoint`/`endpoint_name`/`api_key`/`api_key_env` consistent T4↔engine.
- **No placeholders:** every code/test step is complete.
- **Known real-HF verification point:** `_normalize` field mapping (flagged in the module docstring and the ops follow-up) — cannot be verified until a live endpoint exists.
