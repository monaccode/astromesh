# Centinela Live Endpoint Provisioning — design (infra sub-project)

**Date:** 2026-07-12
**Repo:** astromesh (provisioner + provider auth) — no nebula changes
**Status:** Approved design — ready for implementation plan
**Part of:** Centinela MLOps effort. The four numbered sub-projects (1 foundry catalog,
2 runtime reconciler + provider, 3 docs generator, 4 promotion bot) are shipped. This is
the deferred infra piece: turning the compile-only reconciler into one that actually
provisions HF Inference Endpoints, plus the serving auth needed to call them.

## Purpose

Given the operator's bindings (which alias of which model to serve) and the foundry's
catalog lock (the revision SHA + HF repo), create/update a Hugging Face Inference Endpoint
(TGI, OpenAI-compatible generative serving) for each served binding, and wire the resulting
live URL into the runtime provider config. Close the last gap so the Centinela provider can
actually reach a running, authenticated endpoint.

Scope: a pure endpoint planner, a thin mockable `huggingface_hub` wrapper, an
`apply-endpoints` CLI, a CI workflow that applies on merge, and serving auth + URL fallback
in the provider. No changes to nebula, the foundry, or the training pipeline.

## Context / code reality

- **The reconciler is compile-only.** `astromesh/centinela/reconcile.py::reconcile(lock,
  bindings)` maps `{model, alias, endpoint}` bindings to provider entries, passing the
  hand-set `endpoint` URL straight through. It never calls HF. `_SERVED_KINDS =
  {"classifier", "extractor"}` and the `gate == "passed"` rule live here and are reused.
- **`bindings.yaml`** today: `spec.bindings[] = {model, alias, endpoint}` with `endpoint` a
  placeholder URL (`https://REPLACE_WITH_REAL_HF_ENDPOINT...`). This spec **replaces** the
  `endpoint` input with a declarative `serving:` block; the URL becomes an **output**.
- **The provider sends no auth.** `astromesh/providers/centinela.py::_CentinelaEndpointClient`
  builds `httpx.AsyncClient(base_url=endpoint, timeout=...)` with **no `Authorization`
  header**, and `factory.py::create_provider("centinela", ...)` constructs it with `config={}`
  (a BYOK stub). A protected endpoint would 401. Serving auth is therefore in scope.
- **HF endpoint API** (`huggingface_hub>=0.24`, already a nebula dependency; add to astromesh):
  - `create_inference_endpoint(name, *, repository, framework, task, accelerator, vendor,
    region, type, instance_size, instance_type, revision=None, namespace=None, token=None)
    -> InferenceEndpoint`. `type` ∈ {`"protected"`, `"public"`, `"authenticated"`}; use
    `"protected"` (callable with an org HF token).
  - `get_inference_endpoint(name, *, namespace=None, token=None) -> InferenceEndpoint`
    (raises `HfHubHTTPError` 404 if absent).
  - `endpoint.update(repository=?, revision=?, accelerator=?, instance_size=?,
    instance_type=?) -> InferenceEndpoint` (in-place; status → pending).
  - `endpoint.wait(timeout=?) -> InferenceEndpoint`; `.url` is `None` until `status ==
    "running"`.
- **No trained model yet.** The lock's revision SHAs are placeholders
  (`REPLACE_WITH_REAL_HF_REVISION_SHA`). The planner marks such bindings **not ready** and the
  apply skips them — so merging `serving:` blocks today is a safe no-op. The first real
  endpoint is created when the first model trains. Tests mock HF entirely.
- **HF Jobs precedent:** nebula's `release.yml` already authenticates to HF with an
  `HF_TOKEN` secret and reads an `HF_ORG` var. The astromesh workflow reuses the same secret
  names (`HF_TOKEN`, `vars.HF_ORG`).

## Fixed decisions (from brainstorming)

1. **Apply posture = automatic on merge of bindings** (pure GitOps; the human gate is the
   bindings PR approval). The apply job runs on push to develop/main touching `bindings.yaml`.
2. **Serving config = inline per binding** (`serving:` block on each binding).
3. **Serving auth in scope** — the provider sends `Authorization: Bearer <token>` read from
   the env var named by `api_key_env`; the secret is never committed.
4. **URL delivery = commit + resolve fallback** — the apply job writes the live URL into
   `config/providers.centinela.yaml` and commits it back (primary, auditable); the provider
   falls back to resolving the URL from the endpoint **name** via `get_inference_endpoint`
   when the committed URL is missing/stale.
5. **Keep a `--dry-run`** on the CLI (plan only, no HF mutation) for local runs and an
   optional read-only plan check on PRs — even though the merge job applies.
6. **HF wrapper lives in the `astromesh` package** (not astromesh-node) so the provider can
   reuse resolve-by-name.

## 1. Architecture / data flow

```
config/centinela/bindings.yaml  (operator: model, alias, serving:{…})
   +  catalog.lock.json          (nebula wheel: alias→revision→sha, hf_repo)
        │  (on merge to develop/main touching config/centinela/bindings.yaml)
        ▼
astromesh CI: .github/workflows/centinela-endpoints.yml            [secret HF_TOKEN, var HF_ORG]
   astromeshctl centinela apply-endpoints
     1. plan_endpoints(lock, bindings) -> [DesiredEndpoint]         (PURE)
          · a binding whose revision sha is a placeholder → ready=False → skipped (logged)
     2. per desired: hf.get(name) -> diff_endpoint(desired, actual) -> create | update | noop
     3. hf.wait_url(endpoint) -> live URL
     4. write config/providers.centinela.yaml  (url + endpoint_name + api_key_env: HF_TOKEN)
     5. commit providers.centinela.yaml back  (bot commit, "[skip ci]" to avoid a CI loop)
        ▼
runtime: CentinelaProvider loads providers.yaml -> uses url
         (fallback: get_inference_endpoint(endpoint_name).url)
         -> Authorization: Bearer os.environ[api_key_env]
```

The nebula lock is the source of truth for repo+sha; bindings are the source of truth for
which aliases to serve and on what hardware. The generated `providers.centinela.yaml` is the
only new committed runtime artifact.

## 2. Components

### 2.1 `astromesh/centinela/endpoints.py` — pure planner (no I/O)

Imports the reconciler's serve rules (`_SERVED_KINDS`, the `gate == "passed"` check).

- **`endpoint_name(model: str, alias: str) -> str`** — deterministic, e.g.
  `f"{model}-{alias}"` → `centinela-sentiment-prod`. Lowercased; the source names are already
  kebab. (HF endpoint names must be lowercase and reasonably short — the current names fit.)
- **`plan_endpoints(lock: dict, bindings: dict) -> list[DesiredEndpoint]`** — one entry per
  served binding. Raises `EndpointPlanError` on an unknown model, an alias absent from the
  catalog, a `gate != "passed"` target, or a non-served kind that has a binding (mirrors
  `reconcile`'s errors). `DesiredEndpoint` (frozen dataclass):
  `{name, model, alias, repository (=hf_repo), revision (=rev sha), framework="pytorch",
  task="text-generation", type="protected", vendor, region, accelerator, instance_type,
  instance_size, scale_to_zero, min_replica, max_replica, api_key_env, ready: bool}`.
  `ready` is `False` when the revision sha does not match `^[0-9a-f]{7,40}$` (placeholder →
  model not published yet).
- **`diff_endpoint(desired: DesiredEndpoint, actual: dict | None) -> EndpointAction`** —
  pure, given a normalized `actual` (what the wrapper read back from HF, or `None` if absent):
  - `actual is None` → `create`.
  - `actual` differs on `revision` or any hardware field → `update` (with the changed fields).
  - otherwise → `noop`.

### 2.2 `astromesh/centinela/hf_endpoints.py` — thin `huggingface_hub` wrapper

The only impure/network module; isolated so tests mock it. Small functions, each a direct
pass-through to `huggingface_hub`:

- `get_endpoint(name, *, namespace, token) -> dict | None` — calls `get_inference_endpoint`;
  returns a normalized dict (`{name, repository, revision, accelerator, instance_type,
  instance_size, status, url}`) or `None` on 404.
- `create_endpoint(desired: DesiredEndpoint, *, namespace, token) -> object` — calls
  `create_inference_endpoint(...)` with the desired fields.
- `update_endpoint(name, fields: dict, *, namespace, token) -> object` — fetch + `.update(**fields)`.
- `wait_url(endpoint, *, timeout) -> str` — `endpoint.wait(timeout).url`.
- `resolve_url(name, *, namespace, token) -> str | None` — `get_inference_endpoint(name).url`
  (used by the provider fallback).

`huggingface_hub` is imported lazily inside these functions so importing the module (and the
provider) never requires it at import time.

### 2.3 CLI `astromeshctl centinela apply-endpoints`

Mirrors the existing `reconcile` / `plan-promotion` command shape (typer, `console`,
`print_error`). Options: `--bindings` (default `./config/centinela/bindings.yaml`),
`--out` (default `./config/providers.centinela.yaml`), `--namespace` (default from `HF_ORG`
env), `--dry-run` (default `false`), `--wait-timeout` (default e.g. 1800s). Loads the lock
from the nebula wheel (as the existing command does). For each `DesiredEndpoint`:

- `ready is False` → log "skipped (model not published)" and continue.
- `--dry-run` → compute `diff_endpoint` against `hf.get_endpoint` and print the action; **no
  mutation**, no wait.
- otherwise → execute the action (create/update/noop), `wait_url`, collect the URL.

Assemble a `ProviderConfig` (reuse `reconcile.to_provider_config`) whose entries carry
`endpoint` (live URL), `endpoint_name`, `api_key_env`, plus the existing contract/kind/
revision/sha, and write it to `--out`. Exit non-zero if any endpoint fails to reach a URL.

### 2.4 `.github/workflows/centinela-endpoints.yml`

- `on: push: branches: [develop, main], paths: [config/centinela/bindings.yaml]`.
- Runs from the `astromesh-node/` project env and invokes `apply_endpoints_command` **as a
  Python function** (`uv run python -c '...'`), exactly as sub-project 4's workflow does —
  `astromeshctl` (in astromesh-cli) does not compose the `centinela` plugin, so the binary
  form isn't reachable in CI. The `uv sync` must install `huggingface_hub` (it's added to
  astromesh's `centinela` extra, which astromesh-node pulls transitively). Authenticates with
  `secrets.HF_TOKEN`, passes `vars.HF_ORG`. Real apply (not dry-run).
- Commits the regenerated `config/providers.centinela.yaml` back with a message containing
  `[skip ci]` (avoid an infinite CI loop). If nothing changed, no commit.
- `permissions: contents: write`.

### 2.5 Serving auth + URL fallback — `astromesh/providers/centinela.py` + `factory.py`

- `_CentinelaEndpointClient` accepts `api_key` or `api_key_env` in config: resolve the token
  (`config.get("api_key") or os.environ.get(config["api_key_env"])`) and send
  `Authorization: Bearer <token>` on every request when a token is present. No token → no
  header (local/unprotected dev, unchanged behavior).
- It also accepts `endpoint_name`: when `endpoint` is missing/empty, resolve the URL at
  startup via `hf_endpoints.resolve_url(endpoint_name, ...)` (the commit+fallback decision).
- `factory.create_provider("centinela", ...)` threads `endpoint`, `endpoint_name`,
  `api_key_env`, `contract`, `kind` from the provider config entry (replacing today's
  `config={}` stub) so a routed Centinela provider is actually usable.

## 3. Data model — `config/centinela/bindings.yaml`

Per binding, replace `endpoint:` with:

```yaml
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

The seed `bindings.yaml` is updated to this shape (with example hardware and the placeholder
model, which the planner marks not-ready).

## 4. Errors / edge cases

- **Placeholder revision sha** → `ready=False`, skipped; apply is a no-op. This is today's
  state and must not fail the job.
- **Unknown model / alias absent / gate≠passed / non-served kind bound** → `EndpointPlanError`
  (fail loudly, before any HF call), matching `reconcile`'s contract.
- **HF create/update failure or wait timeout** → the CLI exits non-zero; the workflow fails
  (no partial `providers.yaml` committed for that endpoint). Already-running endpoints for
  other bindings are unaffected (each is independent).
- **`get_endpoint` 404** → treated as "absent" → `create` (not an error).
- **Missing token at apply time** → fail loudly with a clear message (the workflow provides
  `HF_TOKEN`; a local run without it should not silently no-op a mutation).
- **Provider with neither `endpoint` nor a resolvable `endpoint_name`** → falls back to the
  existing localhost default (unchanged dev behavior), no crash.

## 5. Testing (pytest; huggingface_hub fully mocked)

`tests/test_centinela_endpoints.py` (pure planner + diff):
- served binding + real 40-hex sha → one `DesiredEndpoint`, `ready=True`, fields mapped.
- placeholder sha → `ready=False`.
- non-served kind bound → `EndpointPlanError`; unknown model / alias absent / gate≠passed → raises.
- `diff_endpoint`: `actual=None` → create; changed revision → update carrying `revision`;
  changed instance_size → update carrying the hw field; identical → noop.
- `endpoint_name` deterministic.

`tests/test_centinela_hf_endpoints.py` (wrapper, `huggingface_hub` monkeypatched):
- `get_endpoint` returns normalized dict; 404 → `None`.
- `create_endpoint` / `update_endpoint` call the right hf function with mapped kwargs.

`astromesh-node/tests/test_centinela_cli.py` (apply CLI, wrapper monkeypatched):
- create path writes `providers.yaml` with `endpoint` (mock URL) + `endpoint_name` + `api_key_env`.
- `--dry-run` performs no create/update/wait and writes no live URL.
- a not-ready binding is skipped.

`tests/test_centinela_provider.py` (extend):
- with `api_key`/`api_key_env` set → request carries `Authorization: Bearer …` (respx/mock).
- with `endpoint` missing but `endpoint_name` set → resolves URL via mocked `resolve_url`.

Workflow YAML parses (guard the PyYAML `on:` → `True` quirk).

## 6. Out of scope (deferred)

- Multi-region / A-B / canary endpoints; fine-grained autoscaling and SLA metrics.
- Token rotation and per-endpoint distinct serving tokens (single `HF_TOKEN` for now).
- Tearing down endpoints when a binding is removed (this sub-project creates/updates; removal
  is a follow-up so an accidental bindings deletion can't destroy a live endpoint automatically).
- Any change to nebula, the foundry, or the training pipeline.

## File manifest

New (astromesh):
- `astromesh/centinela/endpoints.py` (pure planner)
- `astromesh/centinela/hf_endpoints.py` (huggingface_hub wrapper)
- `tests/test_centinela_endpoints.py`
- `tests/test_centinela_hf_endpoints.py`
- `.github/workflows/centinela-endpoints.yml`

Modified (astromesh):
- `astromesh-node/src/astromesh_node/cli/commands/centinela.py` (add `apply-endpoints`)
- `astromesh-node/tests/test_centinela_cli.py` (apply tests)
- `astromesh/providers/centinela.py` (Bearer auth + endpoint_name fallback)
- `astromesh/providers/factory.py` (thread endpoint/endpoint_name/api_key_env/contract/kind)
- `tests/test_centinela_provider.py` (auth + fallback tests)
- `config/centinela/bindings.yaml` (serving block replaces endpoint)
- `pyproject.toml` (add `huggingface_hub>=0.24` to the `centinela` extra)

Generated (committed by the apply job, not by this sub-project):
- `config/providers.centinela.yaml` (live URL + endpoint_name + api_key_env)
