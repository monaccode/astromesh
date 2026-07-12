# Provider Registry + providerRef — runtime consumes ProviderConfig (design)

**Date:** 2026-07-12
**Repo:** astromesh (runtime engine) — no nebula changes
**Status:** Approved design — ready for implementation plan
**Part of:** Centinela MLOps effort. Closes the discriminator gap flagged by the live-endpoint
sub-project's final review: the generated `config/providers.centinela.yaml` (and any other
`ProviderConfig`) is never read by the runtime, so an agent cannot reference a provisioned
Centinela endpoint without hand-copying endpoint/contract/auth into its own agent spec.

## Purpose

Make the runtime engine load `ProviderConfig` documents at startup into a registry, and let an
agent's model block reference a registry entry by name via a new `providerRef` field. The engine
then fills the block's `source`, `endpoint`, `endpoint_name`, `api_key_env`, `contract`, and
`model` from the referenced entry — closing the loop `bindings → apply-endpoints →
providers.centinela.yaml → agent → live provider` without any manual copy step.

Scope: a small provider-registry loader + a pure `providerRef` resolution step, wired into
`AgentEngine`. No changes to the reconciler, the apply CLI, the provider, nebula, or the
`ProviderConfig` file format.

## Context / code reality

- **The engine never reads any `providers.yaml`.** `AgentEngine.__init__(config_dir="./config")`
  loads agents and RAG specs but not providers. Each agent's `spec.model` (the *model_spec*) is
  normalized by `_normalize_model_spec` into roles → *candidate blocks*; each block is turned into
  a provider by `build_candidate_provider(block)` (engine.py:92), which dispatches on
  `block["source"]` (or legacy `block["provider"]`). The block comes **entirely from the agent
  spec** — nothing merges in an external `ProviderConfig`.
- **`ProviderConfig` shape** (both writers agree): `{apiVersion, kind: ProviderConfig, metadata,
  spec: {providers: {<entry_name>: <entry>}, routing?}}`. Each entry carries a `type`:
  - `init` (`_build_provider_config`, init.py:150) writes entries keyed by **provider name**
    (`ollama`/`openai`/`anthropic`) with `type` = the adapter (`ollama`, `openai_compat`, …),
    plus `endpoint`/`api_key_env`/`models`.
  - `reconcile` / `apply-endpoints` write entries keyed by **model name** (`centinela-sentiment`)
    with `type: centinela`, plus `endpoint`, `endpoint_name`, `api_key_env`, `contract`, `kind`,
    `models`, `revision`, `sha`.
  In both, `spec.providers` is `{name: entry}` and `entry["type"]` selects the adapter — i.e. the
  same discriminator `build_candidate_provider` already dispatches on as `source`.
- **`build_candidate_provider` already reads** `source`, `model`, `endpoint`, `endpoint_name`,
  `api_key`, `api_key_env`, `contract` for the relevant adapters (the centinela block was wired in
  the live-endpoints sub-project). So a resolved block only needs those keys populated — no adapter
  changes required.
- **Reality today:** no `config/providers.centinela.yaml` exists yet (apply-endpoints is a no-op
  until a model trains) and the seed has no `providers.yaml`. So the registry is empty today; this
  change is inert until those files exist, and must not disturb agents that don't use `providerRef`.

## Fixed decisions (from brainstorming)

1. **Agent opt-in = explicit `providerRef` field** on the model block (not name-based auto-fill).
2. **General loader** — load any `config/providers*.yaml` into one registry keyed by entry name;
   the entry's `type` selects the adapter (closes the write-only gap for `init`'s providers.yaml
   too, not just Centinela).
3. **Unresolved `providerRef` → warn + skip** that candidate (consistent with how the engine
   already treats a candidate whose `build_candidate_provider` returns `None`), never fail agent
   startup.
4. **Explicit block fields win** over the referenced entry (fill-only-missing) so BYOK / override /
   hand-authored blocks keep working.

## 1. Architecture / data flow

```
config/providers*.yaml   (init's providers.yaml + apply's providers.centinela.yaml + any others)
   │  AgentEngine.__init__  ->  load_provider_registry(config_dir)
   ▼
self._provider_registry : { entry_name -> entry }        (entry carries type/endpoint/contract/…)
   │
agent spec.model block:  { providerRef: centinela-sentiment }
   │  _build_role_routers  ->  resolve_block(block, registry)   (PURE)
   ▼
resolved block: { source: <entry.type>, model, endpoint, endpoint_name, api_key_env, contract, … }
   │  build_candidate_provider(block)     (unchanged signature)
   ▼
CentinelaProvider (live endpoint + Bearer + contract, all from the entry)
```

Blocks without `providerRef` pass through `resolve_block` unchanged — existing agents are
unaffected.

## 2. Components

### 2.1 `astromesh/runtime/provider_registry.py`

- **`load_provider_registry(config_dir) -> dict[str, dict]`** — glob `config/providers*.yaml` in
  sorted (deterministic) filename order; parse each doc; merge every `spec.providers` entry into one
  dict keyed by entry name. Missing directory / no files / empty or malformed doc → contributes
  nothing (never raises; a malformed file is logged and skipped). A duplicate entry name across
  files → the later (sorted-order) file wins, logged at warning level.
- **`resolve_block(block: dict, registry: dict) -> dict`** — pure, no I/O:
  - No `providerRef` key → return `block` unchanged.
  - `providerRef` names an entry in `registry` → build a base block from the entry:
    `{"source": entry["type"], "model": <entry.models[0] or the entry name>, "endpoint":
    entry.get("endpoint"), "endpoint_name": entry.get("endpoint_name"), "api_key": entry.get("api_key"),
    "api_key_env": entry.get("api_key_env"), "contract": entry.get("contract")}` — then overlay the
    agent block's own keys (minus `providerRef`), so **explicit block fields win**. Drop keys whose
    value is `None` from the overlay so an absent block field doesn't clobber the entry's value.
  - `providerRef` names an unknown entry → return the block with a sentinel that makes the candidate
    skip: the cleanest is to return the block **unchanged except stripped of any `source`/`provider`
    and `model`**, or simpler, return a block with `source="__unresolved__"`. `build_candidate_provider`
    returns `None` for an unknown source, and `_build_role_routers` already logs + skips a `None`
    candidate. (Implementation detail settled in the plan; behavior = warn + skip.)

### 2.2 `astromesh/runtime/engine.py`

- `AgentEngine.__init__`: after `self._config_dir` is set, `self._provider_registry =
  load_provider_registry(self._config_dir)`.
- `_build_role_routers` (or the loop at engine.py:282): before `build_candidate_provider(block)`,
  do `block = resolve_block(block, self._provider_registry)`. No change to
  `build_candidate_provider` itself.

## 3. Errors / edge cases

- **No `providers*.yaml`** → empty registry; blocks without `providerRef` behave exactly as today;
  a block *with* `providerRef` resolves to nothing → warn + skip that candidate.
- **Malformed `providers*.yaml`** (bad YAML / missing `spec.providers`) → logged, contributes no
  entries; other files still load.
- **Duplicate entry name across files** → last (sorted-order) wins, warned.
- **`providerRef` + explicit fields** → explicit fields win; e.g. a block can override `model` while
  inheriting endpoint/contract from the entry.
- **Entry `type` unknown to `build_candidate_provider`** (e.g. a future adapter) → that builder
  returns `None` → warn + skip (no crash).

## 4. Testing (pytest)

`tests/test_provider_registry.py`:
- `load_provider_registry` merges entries from two `providers*.yaml` files into one dict; missing
  dir → `{}`; a malformed file is skipped while a sibling still loads; duplicate name → later file
  wins.
- `resolve_block`: a `providerRef` to a `type: centinela` entry yields a block with `source:
  centinela` + endpoint/endpoint_name/api_key_env/contract; an explicit block `model` overrides the
  entry's; a block with no `providerRef` is returned unchanged; an unresolved `providerRef` yields a
  block that `build_candidate_provider` maps to `None`.

`tests/` engine-level (extend existing engine/wiring tests):
- An `AgentEngine` (or the `_build_role_routers` path) given a registry with a centinela entry and an
  agent block `{providerRef: centinela-sentiment}` registers a working `CentinelaProvider` whose
  client carries the entry's endpoint + contract. Inject the registry directly (no file I/O) or point
  `config_dir` at a tmp dir containing a `providers.centinela.yaml` fixture.

## 5. Out of scope (deferred)

- Hot-reload of the registry (read once at init).
- Consuming `ProviderConfig.spec.routing` / circuit-breaker config (only `spec.providers`).
- Schema validation of `ProviderConfig` beyond skip-on-malformed and warn-on-unknown-type.
- Any change to how `ProviderConfig` files are produced (reconcile/apply/init unchanged).

## File manifest

New:
- `astromesh/runtime/provider_registry.py`
- `tests/test_provider_registry.py`

Modified:
- `astromesh/runtime/engine.py` (load registry at init; `resolve_block` before `build_candidate_provider`)
- an existing engine/wiring test file (or a new test) — the engine-level providerRef case
