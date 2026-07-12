# Provider Registry + providerRef Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the runtime load `config/providers*.yaml` into a registry and let an agent model block `{ providerRef: <name> }` inherit source/endpoint/contract/auth from the referenced entry — closing the loop so a provisioned Centinela endpoint is reachable without hand-copying config.

**Architecture:** A small loader + a pure `resolve_block` in a new `provider_registry` module; `AgentEngine` loads the registry at init and resolves each candidate block before `build_candidate_provider` (whose signature is unchanged).

**Tech Stack:** Python 3.12+, PyYAML (existing), pytest.

## Global Constraints

- **Repo & branch:** all work in **astromesh** on branch `feat/provider-registry` off `develop`.
- **Python:** 3.12+; `ruff` line length 100. No new dependencies (`yaml`, `logging`, `pathlib` all available).
- **Behavior contract:** a block WITHOUT `providerRef` must pass through `resolve_block` unchanged (existing agents unaffected). Explicit block fields (non-`None`) win over the referenced entry. An unresolved `providerRef` yields a block whose `source` `build_candidate_provider` maps to `None` → the engine's existing loop logs + skips it (warn + skip). No file → empty registry (never raises).
- **Entry `type` → block `source`:** the entry's `type` (`centinela`, `openai_compat`, …) becomes the block `source`; `build_candidate_provider` already dispatches on `source`.
- **Do not change** `build_candidate_provider`'s signature, the `ProviderConfig` file format, or the reconcile/apply/init writers.
- **Commits:** Conventional Commits; every commit body ends with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

### Task 1: `provider_registry` module (loader + resolver)

**Files:**
- Create: `astromesh/runtime/provider_registry.py`
- Test: `tests/test_provider_registry.py`

**Interfaces:**
- Produces (used by Task 2): `load_provider_registry(config_dir) -> dict[str, dict]`, `resolve_block(block: dict, registry: dict) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_provider_registry.py
import yaml

from astromesh.runtime.provider_registry import load_provider_registry, resolve_block


def _write(directory, name, doc):
    (directory / name).write_text(yaml.safe_dump(doc))


def _pc(providers):
    return {"apiVersion": "astromesh/v1", "kind": "ProviderConfig",
            "metadata": {"name": "x"}, "spec": {"providers": providers}}


def test_load_merges_multiple_files(tmp_path):
    _write(tmp_path, "providers.yaml",
           _pc({"openai": {"type": "openai_compat", "endpoint": "https://o"}}))
    _write(tmp_path, "providers.centinela.yaml",
           _pc({"centinela-sentiment": {"type": "centinela", "endpoint": "https://c"}}))
    reg = load_provider_registry(tmp_path)
    assert set(reg) == {"openai", "centinela-sentiment"}
    assert reg["centinela-sentiment"]["type"] == "centinela"


def test_load_missing_dir_is_empty(tmp_path):
    assert load_provider_registry(tmp_path / "nope") == {}


def test_load_skips_malformed_keeps_sibling(tmp_path):
    (tmp_path / "providers.bad.yaml").write_text("foo: [1, 2\n")  # unclosed flow seq -> YAMLError
    _write(tmp_path, "providers.centinela.yaml", _pc({"m": {"type": "centinela"}}))
    reg = load_provider_registry(tmp_path)
    assert "m" in reg


def test_load_duplicate_name_later_file_wins(tmp_path):
    _write(tmp_path, "providers.a.yaml", _pc({"dup": {"type": "openai_compat", "endpoint": "A"}}))
    _write(tmp_path, "providers.b.yaml", _pc({"dup": {"type": "openai_compat", "endpoint": "B"}}))
    reg = load_provider_registry(tmp_path)
    assert reg["dup"]["endpoint"] == "B"  # sorted order: a before b, b wins


def test_resolve_centinela_ref_fills_source_and_fields():
    reg = {"centinela-sentiment": {"type": "centinela", "endpoint": "https://ep",
                                   "endpoint_name": "centinela-sentiment-prod",
                                   "api_key_env": "HF_TOKEN",
                                   "contract": {"labels": ["pos", "neg"]},
                                   "models": ["centinela-sentiment"]}}
    out = resolve_block({"providerRef": "centinela-sentiment"}, reg)
    assert out["source"] == "centinela"
    assert out["endpoint"] == "https://ep"
    assert out["endpoint_name"] == "centinela-sentiment-prod"
    assert out["api_key_env"] == "HF_TOKEN"
    assert out["contract"]["labels"] == ["pos", "neg"]
    assert out["model"] == "centinela-sentiment"


def test_resolve_explicit_field_overrides_entry():
    reg = {"m": {"type": "centinela", "endpoint": "https://entry", "models": ["m"]}}
    out = resolve_block({"providerRef": "m", "endpoint": "https://override"}, reg)
    assert out["endpoint"] == "https://override"


def test_resolve_block_without_ref_is_unchanged():
    block = {"source": "openai_compat", "model": "gpt-4o"}
    assert resolve_block(block, {}) == block


def test_resolve_unknown_ref_yields_skippable_block():
    out = resolve_block({"providerRef": "missing"}, {})
    assert out.get("source") not in ("centinela", "openai_compat", "openai", "ollama", "litellm")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_provider_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'astromesh.runtime.provider_registry'`

- [ ] **Step 3: Write the module**

```python
# astromesh/runtime/provider_registry.py
"""Load ProviderConfig documents into a registry and resolve providerRef blocks.

The runtime engine reads config/providers*.yaml at startup into a name->entry registry.
An agent model block { providerRef: <entry_name> } then inherits source/endpoint/contract/
auth from the referenced entry, so a provisioned Centinela endpoint (or any ProviderConfig
entry) is reachable without hand-copying config into the agent spec.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_UNRESOLVED_SOURCE = "__unresolved_provider_ref__"


def load_provider_registry(config_dir) -> dict[str, dict]:
    """Merge every config/providers*.yaml ProviderConfig into one {entry_name: entry} dict."""
    registry: dict[str, dict] = {}
    for path in sorted(Path(config_dir).glob("providers*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text()) or {}
        except (OSError, yaml.YAMLError):
            logger.warning("provider registry: could not parse %s; skipping", path)
            continue
        providers = (doc.get("spec") or {}).get("providers") or {}
        if not isinstance(providers, dict):
            logger.warning("provider registry: %s has no spec.providers mapping; skipping", path)
            continue
        for name, entry in providers.items():
            if not isinstance(entry, dict):
                continue
            if name in registry:
                logger.warning(
                    "provider registry: entry %r in %s overrides an earlier definition", name, path)
            registry[name] = entry
    return registry


def resolve_block(block: dict, registry: dict) -> dict:
    """Resolve a providerRef block against the registry; blocks without providerRef pass through.

    The referenced entry supplies source (its `type`) + endpoint/endpoint_name/api_key/api_key_env/
    contract/model; the agent block's own non-None keys override. An unresolved providerRef yields a
    block whose source build_candidate_provider maps to None (warn + skip in the engine loop).
    """
    ref = block.get("providerRef")
    if not ref:
        return block

    entry = registry.get(ref)
    if entry is None:
        logger.warning(
            "provider registry: providerRef %r not found; candidate will be skipped", ref)
        return {"source": _UNRESOLVED_SOURCE, "providerRef": ref}

    models = entry.get("models") or []
    base = {
        "source": entry.get("type"),
        "model": models[0] if models else ref,
        "endpoint": entry.get("endpoint"),
        "endpoint_name": entry.get("endpoint_name"),
        "api_key": entry.get("api_key"),
        "api_key_env": entry.get("api_key_env"),
        "contract": entry.get("contract"),
    }
    overlay = {k: v for k, v in block.items() if k != "providerRef" and v is not None}
    base.update(overlay)
    return base
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_provider_registry.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Lint**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run ruff check astromesh/runtime/provider_registry.py tests/test_provider_registry.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
git add astromesh/runtime/provider_registry.py tests/test_provider_registry.py
git commit -m "$(cat <<'MSG'
feat(runtime): provider registry loader + providerRef resolver

load_provider_registry merges every config/providers*.yaml into one {name: entry} dict;
resolve_block fills a { providerRef: <name> } block's source/endpoint/contract/auth from the
referenced entry (explicit fields win), and yields a skippable block for an unresolved ref.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
)"
```

---

### Task 2: Wire the registry + resolution into `AgentEngine`

**Files:**
- Modify: `astromesh/runtime/engine.py` (import; load registry in `__init__`; resolve in `_build_role_routers`)
- Test: `tests/test_provider_ref_wiring.py`

**Interfaces:**
- Consumes: `load_provider_registry`, `resolve_block` (Task 1); existing module-level `build_candidate_provider`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_provider_ref_wiring.py
import yaml

from astromesh.providers.centinela import CentinelaProvider
from astromesh.runtime.engine import AgentEngine, build_candidate_provider
from astromesh.runtime.provider_registry import resolve_block


def _providers_doc(providers):
    return {"apiVersion": "astromesh/v1", "kind": "ProviderConfig",
            "metadata": {"name": "g"}, "spec": {"providers": providers}}


def test_provider_ref_resolves_to_centinela_provider():
    reg = {"centinela-sentiment": {"type": "centinela", "endpoint": "https://ep.test",
                                   "contract": {"labels": ["positivo", "negativo"]},
                                   "models": ["centinela-sentiment"]}}
    block = resolve_block({"providerRef": "centinela-sentiment"}, reg)
    prov = build_candidate_provider(block)
    assert isinstance(prov, CentinelaProvider)
    assert prov._client.endpoint == "https://ep.test"


def test_engine_loads_registry_at_init(tmp_path):
    (tmp_path / "providers.centinela.yaml").write_text(yaml.safe_dump(_providers_doc(
        {"centinela-sentiment": {"type": "centinela", "endpoint": "https://ep.test",
                                 "models": ["centinela-sentiment"]}})))
    engine = AgentEngine(config_dir=str(tmp_path))
    assert "centinela-sentiment" in engine._provider_registry


def test_engine_build_role_routers_resolves_provider_ref(tmp_path):
    (tmp_path / "providers.centinela.yaml").write_text(yaml.safe_dump(_providers_doc(
        {"centinela-sentiment": {"type": "centinela", "endpoint": "https://ep.test",
                                 "contract": {"labels": ["positivo"]},
                                 "models": ["centinela-sentiment"]}})))
    engine = AgentEngine(config_dir=str(tmp_path))
    routers = engine._build_role_routers({"default": {"providerRef": "centinela-sentiment"}})
    provs = list(routers["default"]._providers.values())  # ModelRouter stores providers here
    assert len(provs) == 1
    assert isinstance(provs[0], CentinelaProvider)
    assert provs[0]._client.endpoint == "https://ep.test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_provider_ref_wiring.py -v`
Expected: FAIL — `AttributeError: 'AgentEngine' object has no attribute '_provider_registry'` (and the resolve import path not yet wired).

- [ ] **Step 3: Add the import**

At the top of `astromesh/runtime/engine.py`, add to the imports:

```python
from astromesh.runtime.provider_registry import load_provider_registry, resolve_block
```

- [ ] **Step 4: Load the registry in `__init__`**

In `AgentEngine.__init__` (engine.py:167-175), after `self._config_dir = Path(config_dir)`, add:

```python
        self._provider_registry = load_provider_registry(self._config_dir)
```

- [ ] **Step 5: Resolve each block in `_build_role_routers`**

In `_build_role_routers` (engine.py:275-306), inside the candidates loop, resolve the block before building. Change:

```python
            for i, block in enumerate(cfg.get("candidates", [])):
                try:
                    prov = build_candidate_provider(block)
```

to:

```python
            for i, block in enumerate(cfg.get("candidates", [])):
                block = resolve_block(block, self._provider_registry)
                try:
                    prov = build_candidate_provider(block)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_provider_ref_wiring.py tests/test_centinela_wiring.py -v`
Expected: PASS (new wiring tests + existing centinela wiring tests still green).

- [ ] **Step 7: Lint & commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
uv run ruff check astromesh/runtime/engine.py tests/test_provider_ref_wiring.py
git add astromesh/runtime/engine.py tests/test_provider_ref_wiring.py
git commit -m "$(cat <<'MSG'
feat(runtime): AgentEngine resolves providerRef against the provider registry

The engine loads config/providers*.yaml at init and resolves each candidate block through
resolve_block before build_candidate_provider, so an agent block { providerRef: <name> }
gets its source/endpoint/contract/auth from the generated ProviderConfig. Blocks without
providerRef are untouched.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
)"
```

---

## Post-implementation (controller, after all tasks)

- Full suites green: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest -q` (use `--extra all` when syncing so optional-dep tests collect). Ruff clean.
- Final whole-branch review, then `superpowers:finishing-a-development-branch`. Pushing is outward-facing — confirm with the user first.
- **Note for the PR:** this closes the runtime-consumes-ProviderConfig leg. An agent now selects a provisioned Centinela model with `spec.model.default: { providerRef: centinela-sentiment }`. The registry is read once at engine init (no hot-reload).

## Self-review notes

- **Spec coverage:** loader (§2.1)→T1; `resolve_block` (§2.1)→T1; engine wiring (§2.2)→T2. All covered.
- **Type consistency:** `load_provider_registry`/`resolve_block` signatures identical across T1→T2; `resolve_block` output keys (`source`/`model`/`endpoint`/`endpoint_name`/`api_key`/`api_key_env`/`contract`) match what `build_candidate_provider` reads.
- **No placeholders:** every code/test step is complete.
