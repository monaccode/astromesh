# Centinela Promotion Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate GitOps steps 6 and 9 — when nebula publishes a new `catalog.lock.json`, an astromesh workflow opens a human-merged PR that syncs the lock and summarizes the promotion.

**Architecture:** A pure Python planner (`plan_promotion`) diffs the old (vendored) lock against the new one and produces a `PromotionPlan`; a thin `astromeshctl centinela plan-promotion` CLI applies the file edits (refresh vendored lock, bump the `astromesh-nebula` pin, stub missing bindings) and renders the PR body. Two thin GitHub Actions workflows wire it: nebula fires `repository_dispatch` on lock change; astromesh runs the CLI and opens the PR. No live HF endpoints — the bot emits stubs.

**Tech Stack:** Python 3.11+, typer, PyYAML (all existing deps), pytest; GitHub Actions (`peter-evans/create-pull-request`).

## Global Constraints

- **Repos & branches:** Tasks 1–4 in **astromesh** on branch `feat/centinela-promotion-bot` off `develop`. Task 5 in **astromesh-nebula** on branch `feat/centinela-notify-dispatch` off `develop`.
- **Python:** 3.11+ (astromesh targets 3.12+; nebula 3.11+). `ruff` line length 100.
- **Zero new runtime dependencies.** Planner uses only stdlib; CLI uses typer + PyYAML (already deps). `peter-evans/create-pull-request` is a GitHub Action, not a Python dep.
- **Schema:** support `schema_version == "1"` only (string); anything else raises.
- **Reuse, don't redefine:** import `_SERVED_KINDS` from `astromesh/centinela/reconcile.py` so "served" means the same thing as the reconciler.
- **Stub endpoint literal:** `https://REPLACE_WITH_REAL_HF_ENDPOINT.endpoints.huggingface.cloud`. The bot never fabricates a real endpoint or SHA.
- **Dispatch contract:** event type `catalog-lock-updated`; `client_payload` = `{ref, version, sha}`.
- **Commits:** Conventional Commits; every commit body ends with the trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Test fixtures** are plain `dict` literals (match `tests/test_centinela_reconcile.py`). Lock shape per model: `{name, kind, task, vertical, hf_repo, contract, aliases:{<alias>:<rev>}, revisions:{<rev>:{version, sha, gate, eval:{macro_f1, invalid_rate}}}}`.

---

### Task 1: Pure planner core (`plan_promotion` + plan types)

**Files:**
- Create: `astromesh/centinela/promote.py`
- Test: `tests/test_centinela_promote.py`

**Interfaces:**
- Consumes: `astromesh.centinela.reconcile._SERVED_KINDS` (a `set[str]`, currently `{"classifier", "extractor"}`).
- Produces (relied on by Tasks 2 and 3):
  - `class PromoteError(ValueError)`
  - frozen dataclasses `AliasMove(model, alias, from_rev: str|None, to_rev: str, from_eval: dict|None, to_eval: dict|None)`, `MissingBinding(model, alias)`, `Blocked(model, alias, reason)`
  - `PromotionPlan(alias_moves: list[AliasMove], missing_bindings: list[MissingBinding], blocked: list[Blocked])` with property `is_noop: bool`
  - `plan_promotion(old_lock: dict, new_lock: dict, bindings: dict) -> PromotionPlan`
  - `_eval_of(model: dict | None, rev_key: str | None) -> dict | None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_centinela_promote.py
import pytest

from astromesh.centinela.promote import (
    Blocked,
    MissingBinding,
    PromoteError,
    plan_promotion,
)


def _rev(rev, gate="passed", f1=0.9, inv=0.01):
    return {"version": rev, "sha": "a" * 40, "gate": gate,
            "eval": {"macro_f1": f1, "invalid_rate": inv}}


def _model(name="centinela-sentiment", kind="classifier", aliases=None, revisions=None):
    return {
        "name": name, "kind": kind, "task": "text-classification",
        "vertical": "finanzas", "hf_repo": "astromesh/Centinela-Qwen3-4B",
        "contract": {"labels": ["positivo", "neutral", "negativo"]},
        "aliases": aliases if aliases is not None else {"prod": "v0.1"},
        "revisions": revisions if revisions is not None else {"v0.1": _rev("v0.1")},
    }


def _lock(models):
    return {"schema_version": "1", "models": models}


def _bindings(entries):
    return {"apiVersion": "astromesh/v1", "kind": "CentinelaBindings",
            "metadata": {"name": "default"}, "spec": {"bindings": entries}}


BIND_PROD = [{"model": "centinela-sentiment", "alias": "prod",
              "endpoint": "https://ep.example.cloud"}]


def test_staging_alias_moved_with_binding_is_a_clean_move():
    old = _lock([_model(aliases={"staging": "v0.1"},
                        revisions={"v0.1": _rev("v0.1"), "v0.2": _rev("v0.2")})])
    new = _lock([_model(aliases={"staging": "v0.2"},
                        revisions={"v0.1": _rev("v0.1"), "v0.2": _rev("v0.2")})])
    bindings = _bindings([{"model": "centinela-sentiment", "alias": "staging",
                           "endpoint": "https://ep.example.cloud"}])
    plan = plan_promotion(old, new, bindings)
    assert len(plan.alias_moves) == 1
    assert plan.alias_moves[0].from_rev == "v0.1"
    assert plan.alias_moves[0].to_rev == "v0.2"
    assert plan.missing_bindings == []
    assert plan.blocked == []
    assert plan.is_noop is False


def test_new_served_alias_without_binding_is_missing():
    old = _lock([_model(aliases={}, revisions={"v0.1": _rev("v0.1")})])
    new = _lock([_model(aliases={"staging": "v0.1"}, revisions={"v0.1": _rev("v0.1")})])
    plan = plan_promotion(old, new, _bindings([]))
    assert plan.missing_bindings == [MissingBinding("centinela-sentiment", "staging")]


def test_bound_alias_moved_to_failing_gate_is_blocked():
    old = _lock([_model(aliases={"prod": "v0.1"},
                        revisions={"v0.1": _rev("v0.1"), "v0.2": _rev("v0.2", gate="pending")})])
    new = _lock([_model(aliases={"prod": "v0.2"},
                        revisions={"v0.1": _rev("v0.1"), "v0.2": _rev("v0.2", gate="pending")})])
    plan = plan_promotion(old, new, _bindings(BIND_PROD))
    assert len(plan.blocked) == 1
    assert plan.blocked[0].alias == "prod"
    assert plan.alias_moves == []  # a blocked move is not also reported clean


def test_removed_revision_under_bound_alias_is_blocked():
    old = _lock([_model(aliases={"prod": "v0.1"}, revisions={"v0.1": _rev("v0.1")})])
    new = _lock([_model(aliases={"prod": "v0.1"}, revisions={})])  # v0.1 gone
    plan = plan_promotion(old, new, _bindings(BIND_PROD))
    assert len(plan.blocked) == 1
    assert "absent" in plan.blocked[0].reason


def test_identical_locks_is_noop():
    lock = _lock([_model()])
    plan = plan_promotion(lock, lock, _bindings(BIND_PROD))
    assert plan.is_noop is True


def test_non_served_kind_alias_is_not_flagged_missing():
    old = _lock([_model(name="centinela-chat", kind="instruct", aliases={},
                        revisions={"v1": _rev("v1")})])
    new = _lock([_model(name="centinela-chat", kind="instruct", aliases={"prod": "v1"},
                        revisions={"v1": _rev("v1")})])
    plan = plan_promotion(old, new, _bindings([]))
    assert plan.missing_bindings == []


def test_unsupported_schema_version_raises():
    new = {"schema_version": "2", "models": []}
    with pytest.raises(PromoteError):
        plan_promotion(_lock([]), new, _bindings([]))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_centinela_promote.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'astromesh.centinela.promote'`

- [ ] **Step 3: Write the planner**

```python
# astromesh/centinela/promote.py
"""Plan a Centinela catalog promotion: diff two locks against the operator's bindings.

Pure logic, no I/O. Given the previous (vendored) catalog lock, the newly published
lock, and `bindings.yaml`, produce a PromotionPlan describing which aliases moved, which
served aliases still need an endpoint binding, and which bound aliases are now unservable.
The CLI wrapper turns a plan into file edits + a PR body.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from astromesh.centinela.reconcile import _SERVED_KINDS

_SUPPORTED_SCHEMA = "1"


class PromoteError(ValueError):
    """The new lock cannot be planned against (e.g. unsupported schema)."""


@dataclass(frozen=True)
class AliasMove:
    model: str
    alias: str
    from_rev: str | None
    to_rev: str
    from_eval: dict | None
    to_eval: dict | None


@dataclass(frozen=True)
class MissingBinding:
    model: str
    alias: str


@dataclass(frozen=True)
class Blocked:
    model: str
    alias: str
    reason: str


@dataclass(frozen=True)
class PromotionPlan:
    alias_moves: list[AliasMove] = field(default_factory=list)
    missing_bindings: list[MissingBinding] = field(default_factory=list)
    blocked: list[Blocked] = field(default_factory=list)

    @property
    def is_noop(self) -> bool:
        return not (self.alias_moves or self.missing_bindings or self.blocked)


def _eval_of(model: dict | None, rev_key: str | None) -> dict | None:
    """Return the eval block of a revision, or None if absent."""
    if not model or rev_key is None:
        return None
    return model.get("revisions", {}).get(rev_key, {}).get("eval")


def plan_promotion(old_lock: dict, new_lock: dict, bindings: dict) -> PromotionPlan:
    """Diff old vs new lock against the bindings; classify every changed alias."""
    if str(new_lock.get("schema_version")) != _SUPPORTED_SCHEMA:
        raise PromoteError(
            f"unsupported schema_version {new_lock.get('schema_version')!r}; expected '1'"
        )

    old_models = {m["name"]: m for m in old_lock.get("models", [])}
    new_models = {m["name"]: m for m in new_lock.get("models", [])}
    bound = {
        (b["model"], b["alias"])
        for b in bindings.get("spec", {}).get("bindings", [])
    }

    moves: list[AliasMove] = []
    missing: list[MissingBinding] = []
    blocked: list[Blocked] = []

    for name, model in new_models.items():
        old_model = old_models.get(name)
        old_aliases = (old_model or {}).get("aliases", {})
        served = model.get("kind") in _SERVED_KINDS
        revisions = model.get("revisions", {})

        for alias, target in model.get("aliases", {}).items():
            is_bound = (name, alias) in bound
            old_target = old_aliases.get(alias)
            rev = revisions.get(target)

            if rev is None:
                if is_bound:
                    blocked.append(Blocked(
                        name, alias,
                        f"alias '{alias}' points at '{target}', absent from the new lock",
                    ))
                continue

            if old_target == target:
                continue  # unchanged and valid — nothing to do

            if rev.get("gate") != "passed":
                if is_bound:
                    blocked.append(Blocked(
                        name, alias,
                        f"{name}:{target} has gate '{rev.get('gate')}', "
                        "only 'passed' may be served",
                    ))
                continue  # unbound + bad gate: not servable, no action

            moves.append(AliasMove(
                name, alias, old_target, target,
                _eval_of(old_model, old_target), _eval_of(model, target),
            ))
            if served and not is_bound:
                missing.append(MissingBinding(name, alias))

    for name, alias in bound:
        new_model = new_models.get(name)
        if new_model is None:
            blocked.append(Blocked(name, alias, f"model '{name}' removed from the new lock"))
        elif alias not in new_model.get("aliases", {}):
            blocked.append(Blocked(
                name, alias, f"alias '{alias}' removed from model '{name}' in the new lock",
            ))

    return PromotionPlan(moves, missing, blocked)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_centinela_promote.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Lint**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run ruff check astromesh/centinela/promote.py tests/test_centinela_promote.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
git add astromesh/centinela/promote.py tests/test_centinela_promote.py
git commit -m "$(cat <<'MSG'
feat(centinela): pure catalog promotion planner

plan_promotion() diffs the vendored lock against a newly published lock and
classifies each changed alias into moves, missing endpoint bindings, and blocked
(unservable) aliases, reusing the reconciler's _SERVED_KINDS + gate rules.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
)"
```

---

### Task 2: PR rendering + apply helpers (labels, body, stub, pin bump)

**Files:**
- Modify: `astromesh/centinela/promote.py` (append helpers)
- Modify: `tests/test_centinela_promote.py` (append tests)

**Interfaces:**
- Consumes: `PromotionPlan`, `AliasMove`, `MissingBinding`, `Blocked` from Task 1.
- Produces (relied on by Task 3):
  - `pr_labels(plan: PromotionPlan) -> list[str]`
  - `stub_binding(model: str, alias: str) -> dict` → `{"model", "alias", "endpoint"}`
  - `render_pr_body(plan: PromotionPlan, version: str) -> str`
  - `bump_nebula_pin(text: str, version: str) -> str`
  - module constant `STUB_ENDPOINT: str`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_centinela_promote.py
from astromesh.centinela.promote import (  # noqa: E402  (grouped with existing imports)
    AliasMove,
    PromotionPlan,
    bump_nebula_pin,
    pr_labels,
    render_pr_body,
    stub_binding,
)


def _move(alias="staging", frm="v0.1", to="v0.2", f1_from=0.90, f1_to=0.93):
    return AliasMove("centinela-sentiment", alias, frm, to,
                     {"macro_f1": f1_from, "invalid_rate": 0.02},
                     {"macro_f1": f1_to, "invalid_rate": 0.01})


def test_pr_labels_prod_when_prod_alias_moved():
    plan = PromotionPlan(alias_moves=[_move(alias="prod")])
    assert "centinela:prod" in pr_labels(plan)
    assert "centinela:staging" not in pr_labels(plan)


def test_pr_labels_staging_default_and_blocked_marker():
    plan = PromotionPlan(alias_moves=[_move(alias="staging")],
                         blocked=[Blocked("m", "staging", "bad")])
    labels = pr_labels(plan)
    assert "centinela:staging" in labels
    assert "centinela:blocked" in labels


def test_stub_binding_shape():
    b = stub_binding("centinela-sentiment", "prod")
    assert b["model"] == "centinela-sentiment"
    assert b["alias"] == "prod"
    assert b["endpoint"].startswith("https://REPLACE_WITH_REAL_HF_ENDPOINT")


def test_render_pr_body_has_eval_delta_and_checklist():
    plan = PromotionPlan(alias_moves=[_move()],
                         missing_bindings=[MissingBinding("centinela-sentiment", "staging")])
    body = render_pr_body(plan, "0.2.0")
    assert "0.9 → 0.93" in body
    assert "- [ ]" in body           # a checklist item for the missing binding
    assert "centinela-sentiment" in body


def test_bump_nebula_pin_rewrites_version():
    assert bump_nebula_pin('centinela = ["astromesh-nebula>=0.1.0"]', "0.2.0") == \
        'centinela = ["astromesh-nebula>=0.2.0"]'
    assert bump_nebula_pin('    "astromesh-nebula>=0.1.0",', "0.3.1") == \
        '    "astromesh-nebula>=0.3.1",'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_centinela_promote.py -k "labels or stub or render or bump" -v`
Expected: FAIL — `ImportError: cannot import name 'pr_labels'`

- [ ] **Step 3: Append the helpers**

```python
# append to astromesh/centinela/promote.py
import re

STUB_ENDPOINT = "https://REPLACE_WITH_REAL_HF_ENDPOINT.endpoints.huggingface.cloud"
_PIN_RE = re.compile(r"astromesh-nebula>=[^\"']*")


def pr_labels(plan: PromotionPlan) -> list[str]:
    """Label the PR: prod if a prod alias is involved, else staging; mark blocked."""
    prod = any(m.alias == "prod" for m in plan.alias_moves) or \
        any(b.alias == "prod" for b in plan.blocked)
    labels = ["centinela:prod"] if prod else ["centinela:staging"]
    if plan.blocked:
        labels.append("centinela:blocked")
    return labels


def stub_binding(model: str, alias: str) -> dict:
    """A placeholder binding a human must complete with a real endpoint URL."""
    return {"model": model, "alias": alias, "endpoint": STUB_ENDPOINT}


def _fmt_delta(from_eval: dict | None, to_eval: dict | None, key: str) -> str:
    to_v = (to_eval or {}).get(key)
    from_v = (from_eval or {}).get(key)
    if to_v is None:
        return "—"
    if from_v is None:
        return f"{to_v}"
    return f"{from_v} → {to_v}"


def render_pr_body(plan: PromotionPlan, version: str) -> str:
    """Render the promotion summary + human checklist as Markdown."""
    prod = any(m.alias == "prod" for m in plan.alias_moves)
    lines = ["# ⬆️ Centinela PROD promotion" if prod else "# Centinela staging sync", ""]
    lines += [f"Nebula catalog version: `{version}`", ""]

    if plan.alias_moves:
        lines += ["## Alias moves", "",
                  "| model | alias | from | to | macro_f1 | invalid_rate |",
                  "|-------|-------|------|----|----------|--------------|"]
        for m in plan.alias_moves:
            f1 = _fmt_delta(m.from_eval, m.to_eval, "macro_f1")
            inv = _fmt_delta(m.from_eval, m.to_eval, "invalid_rate")
            lines.append(f"| {m.model} | {m.alias} | {m.from_rev or '—'} | {m.to_rev} | {f1} | {inv} |")
        lines.append("")

    if plan.missing_bindings:
        lines += ["## ⚠️ Missing endpoint bindings", "",
                  "A stub was added to `config/centinela/bindings.yaml`. "
                  "Provide the live endpoint URL before merge:", ""]
        for mb in plan.missing_bindings:
            lines.append(f"- [ ] set the endpoint for `{mb.model}` / `{mb.alias}`")
        lines.append("")

    if plan.blocked:
        lines += ["## 🚫 Blocked — do not merge until resolved", ""]
        for b in plan.blocked:
            lines.append(f"- `{b.model}` / `{b.alias}`: {b.reason}")
        lines.append("")

    return "\n".join(lines)


def bump_nebula_pin(text: str, version: str) -> str:
    """Rewrite every `astromesh-nebula>=…` constraint to `>=<version>`."""
    return _PIN_RE.sub(f"astromesh-nebula>={version}", text)
```

Note: move the `import re` to the top of the file with the other imports (below `from __future__`), keeping ruff import-order happy. The code block shows it inline for clarity.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_centinela_promote.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Lint**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run ruff check astromesh/centinela/promote.py tests/test_centinela_promote.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
git add astromesh/centinela/promote.py tests/test_centinela_promote.py
git commit -m "$(cat <<'MSG'
feat(centinela): promotion PR rendering + apply helpers

pr_labels/render_pr_body summarize a plan (eval deltas, missing-binding checklist,
blocked warnings); stub_binding and bump_nebula_pin are the edit primitives the CLI
applies.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
)"
```

---

### Task 3: `astromeshctl centinela plan-promotion` CLI

**Files:**
- Modify: `astromesh-node/src/astromesh_node/cli/commands/centinela.py` (add command + helpers)
- Modify: `astromesh-node/tests/test_centinela_cli.py` (append tests)

**Interfaces:**
- Consumes: `plan_promotion`, `PromoteError`, `render_pr_body`, `pr_labels`, `stub_binding`, `bump_nebula_pin` from `astromesh.centinela.promote`.
- Produces: CLI command `plan-promotion` with options `--new-lock`, `--version`, `--bindings`, `--vendored-lock`, `--pr-body`, `--labels-out`, `--pyproject` (repeatable). Exit codes: `0` ok/noop, `1` blocked (edits + body still written), `2` planning error.

- [ ] **Step 1: Write the failing tests**

Place the new imports with the existing top-of-file imports (`from pathlib import Path`, `import yaml`, `from astromesh_node.cli.commands import centinela`) to avoid ruff E402, then append the test functions below.

```python
# add to the import block at the top of astromesh-node/tests/test_centinela_cli.py
import json

import pytest
import typer

from astromesh.centinela.promote import STUB_ENDPOINT


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest astromesh-node/tests/test_centinela_cli.py -k plan_promotion -v`
Expected: FAIL — `AttributeError: module 'astromesh_node.cli.commands.centinela' has no attribute 'plan_promotion_command'`

- [ ] **Step 3: Add the command + I/O helpers**

Add these imports at the top of `centinela.py` (merge with existing import block):

```python
from typing import Optional

from astromesh.centinela.promote import (
    PromoteError,
    bump_nebula_pin,
    plan_promotion,
    pr_labels,
    render_pr_body,
    stub_binding,
)
```

Append the command and helpers:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest astromesh-node/tests/test_centinela_cli.py -v`
Expected: PASS (existing reconcile tests + 4 new plan_promotion tests)

- [ ] **Step 5: Lint**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run ruff check astromesh-node/src/astromesh_node/cli/commands/centinela.py astromesh-node/tests/test_centinela_cli.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
git add astromesh-node/src/astromesh_node/cli/commands/centinela.py astromesh-node/tests/test_centinela_cli.py
git commit -m "$(cat <<'MSG'
feat(centinela): plan-promotion CLI

astromeshctl centinela plan-promotion diffs the vendored lock against a new one,
refreshes the vendored copy, bumps the astromesh-nebula pin, stubs missing bindings,
and writes the PR body + labels. Exit 1 signals a blocked promotion (PR still opened),
exit 2 a planning error.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
)"
```

---

### Task 4: astromesh workflow — `centinela-sync.yml`

**Files:**
- Create: `.github/workflows/centinela-sync.yml`
- Test: `tests/test_workflow_yaml.py` (create — parses the workflow so a syntax error fails CI)

**Interfaces:**
- Consumes: the `plan_promotion_command` function from Task 3 (`astromesh_node.cli.commands.centinela`); repo variable `NEBULA_REPO` (e.g. `monaccode/astromesh-nebula`); secret `GH_PIPELINE_TOKEN`.
- Produces: a PR on branch `bot/centinela-sync`.

**Env note (important — the plan-promotion command is NOT reachable via the `astromeshctl` binary in CI).** `astromeshctl` is defined in the separate `astromesh-cli` project, which depends only on `astromesh` — it does **not** compose the `centinela` plugin (registered by `astromesh-node`'s entry-point) or `astromesh-nebula`. There is no env in this repo where `astromeshctl centinela plan-promotion` runs. So the workflow invokes the command **as a Python function from the `astromesh-node` project's env** (which has `astromesh`, `astromesh-nebula`, `typer`, and the command itself), exactly as the unit tests do. It runs in `astromesh-node/` and passes repo-root-relative (`../…`) paths.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_yaml.py
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]


def test_centinela_sync_workflow_parses():
    wf = yaml.safe_load((_ROOT / ".github/workflows/centinela-sync.yml").read_text())
    # PyYAML parses the bare key `on:` as the boolean True (YAML 1.1), not "on".
    on = wf.get("on", wf.get(True))
    assert "catalog-lock-updated" in on["repository_dispatch"]["types"]
    steps = wf["jobs"]["sync"]["steps"]
    # the command is invoked as a Python function (astromeshctl can't compose the plugin in CI)
    assert any("plan_promotion_command" in str(s.get("run", "")) for s in steps)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_workflow_yaml.py -v`
Expected: FAIL — `FileNotFoundError: .github/workflows/centinela-sync.yml`

- [ ] **Step 3: Write the workflow**

```yaml
# .github/workflows/centinela-sync.yml
name: centinela-sync
on:
  repository_dispatch:
    types: [catalog-lock-updated]

permissions:
  contents: write
  pull-requests: write

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - uses: astral-sh/setup-uv@v7

      - name: Fetch new catalog lock from nebula
        env:
          GH_TOKEN: ${{ secrets.GH_PIPELINE_TOKEN }}
          REF: ${{ github.event.client_payload.ref }}
          NEBULA_REPO: ${{ vars.NEBULA_REPO }}
        run: |
          curl -fsSL \
            -H "Authorization: Bearer $GH_TOKEN" \
            -H "Accept: application/vnd.github.raw" \
            "https://api.github.com/repos/$NEBULA_REPO/contents/nebula/catalog.lock.json?ref=$REF" \
            -o new_lock.json

      - name: Plan promotion
        id: plan
        working-directory: astromesh-node
        env:
          VERSION: ${{ github.event.client_payload.version }}
        run: |
          uv sync --extra test
          set +e
          uv run python -c '
          import os, sys, typer
          from astromesh_node.cli.commands.centinela import plan_promotion_command
          try:
              plan_promotion_command(
                  new_lock="../new_lock.json",
                  version=os.environ["VERSION"],
                  bindings="../config/centinela/bindings.yaml",
                  vendored_lock="../docs-site/src/data/catalog.lock.json",
                  pr_body="../pr-body.md",
                  labels_out="../pr-labels.txt",
                  pyproject=["../pyproject.toml", "../astromesh-node/pyproject.toml"],
              )
          except typer.Exit as exc:
              sys.exit(exc.exit_code or 0)
          '
          code=$?
          set -e
          echo "exit=$code" >> "$GITHUB_OUTPUT"
          cd ..
          if [ -f pr-labels.txt ]; then
            echo "labels=$(cat pr-labels.txt)" >> "$GITHUB_OUTPUT"
          else
            echo "labels=centinela:staging" >> "$GITHUB_OUTPUT"
          fi
          if [ -s pr-body.md ]; then echo "skip=false" >> "$GITHUB_OUTPUT"; else echo "skip=true" >> "$GITHUB_OUTPUT"; fi
          rm -f new_lock.json

      - name: Create pull request
        if: steps.plan.outputs.skip == 'false'
        uses: peter-evans/create-pull-request@v6
        with:
          branch: bot/centinela-sync
          title: "chore(centinela): sync catalog ${{ github.event.client_payload.version }}"
          body-path: pr-body.md
          labels: ${{ steps.plan.outputs.labels }}
          add-paths: |
            docs-site/src/data/catalog.lock.json
            config/centinela/bindings.yaml
            pyproject.toml
            astromesh-node/pyproject.toml

      - name: Fail the check if blocked
        if: steps.plan.outputs.exit == '1'
        run: |
          echo "::error::Blocked promotion — resolve items in the PR body before merge"
          exit 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_workflow_yaml.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
git add .github/workflows/centinela-sync.yml tests/test_workflow_yaml.py
git commit -m "$(cat <<'MSG'
feat(centinela): sync workflow reacting to nebula dispatch

On repository_dispatch(catalog-lock-updated), fetch the new lock from nebula, run
plan-promotion, and open/update the bot/centinela-sync PR (labels from the plan;
failing check when blocked). Never auto-merged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
)"
```

---

### Task 5: nebula workflow — `notify-catalog.yml`

**Files:**
- Create: `.github/workflows/notify-catalog.yml` (in the **astromesh-nebula** repo)
- Test: `tests/test_notify_workflow.py` (in **astromesh-nebula**)

**Interfaces:**
- Consumes: repo variable `ASTROMESH_REPO` (e.g. `monaccode/astromesh`); secret `GH_PIPELINE_TOKEN`.
- Produces: a `repository_dispatch` to astromesh with `{ref, version, sha}`.

- [ ] **Step 0: Create the branch**

```bash
cd /Users/fulfaro/monaccode/astromesh-nebula
git checkout develop && git checkout -b feat/centinela-notify-dispatch
```

- [ ] **Step 1: Write the failing test**

```python
# tests/test_notify_workflow.py  (astromesh-nebula)
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]


def test_notify_workflow_parses_and_targets_lock():
    wf = yaml.safe_load((_ROOT / ".github/workflows/notify-catalog.yml").read_text())
    # PyYAML parses the bare key `on:` as the boolean True (YAML 1.1), not "on".
    push = wf.get("on", wf.get(True))["push"]
    assert "nebula/catalog.lock.json" in push["paths"]
    step_runs = " ".join(str(s.get("run", "")) for s in wf["jobs"]["notify"]["steps"])
    assert "catalog-lock-updated" in step_runs
    assert "dispatches" in step_runs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fulfaro/monaccode/astromesh-nebula && uv run pytest tests/test_notify_workflow.py -v`
Expected: FAIL — `FileNotFoundError`

- [ ] **Step 3: Write the workflow**

```yaml
# .github/workflows/notify-catalog.yml  (astromesh-nebula)
name: notify-catalog
on:
  push:
    branches: [develop, main]
    paths: [nebula/catalog.lock.json]

jobs:
  notify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Read nebula version
        id: ver
        run: |
          version=$(grep -m1 '^version' pyproject.toml | sed -E 's/.*"(.*)".*/\1/')
          echo "version=$version" >> "$GITHUB_OUTPUT"

      - name: Dispatch catalog-lock-updated to astromesh
        env:
          GH_TOKEN: ${{ secrets.GH_PIPELINE_TOKEN }}
          ASTROMESH_REPO: ${{ vars.ASTROMESH_REPO }}
          VERSION: ${{ steps.ver.outputs.version }}
          SHA: ${{ github.sha }}
        run: |
          curl -fsSL -X POST \
            -H "Authorization: Bearer $GH_TOKEN" \
            -H "Accept: application/vnd.github+json" \
            "https://api.github.com/repos/$ASTROMESH_REPO/dispatches" \
            -d "{\"event_type\":\"catalog-lock-updated\",\"client_payload\":{\"ref\":\"$SHA\",\"version\":\"$VERSION\",\"sha\":\"$SHA\"}}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/fulfaro/monaccode/astromesh-nebula && uv run pytest tests/test_notify_workflow.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fulfaro/monaccode/astromesh-nebula
git add .github/workflows/notify-catalog.yml tests/test_notify_workflow.py
git commit -m "$(cat <<'MSG'
feat(centinela): dispatch to astromesh on catalog lock change

On push to develop/main touching nebula/catalog.lock.json, fire a repository_dispatch
(catalog-lock-updated) carrying {ref, version, sha} so the astromesh sync bot opens a
promotion PR.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
)"
```

---

## Post-implementation (controller, after all tasks)

- Full suites green: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest -q` and `cd /Users/fulfaro/monaccode/astromesh-nebula && uv run pytest -q`.
- Ruff clean in both repos.
- **Manual/ops follow-up (not code, note in PR):** set repo variables `NEBULA_REPO` / `ASTROMESH_REPO` and confirm `GH_PIPELINE_TOKEN` has `contents:write` + `pull-requests:write` on astromesh and dispatch rights. These are configured in GitHub settings, not in this plan.
- Final whole-branch review, then `superpowers:finishing-a-development-branch` for each repo's branch (astromesh `feat/centinela-promotion-bot`, nebula `feat/centinela-notify-dispatch`). Pushing is outward-facing — confirm with the user first.

## Self-review notes

- **Spec coverage:** planner (§2.1)→T1/T2; CLI (§2.2)→T3; astromesh workflow (§2.3)→T4; nebula workflow (§2.4)→T5; missing-binding stub (§3)→T2/T3; blocked-still-PRs (§4)→T3/T4; testing (§5)→each task's tests. All covered.
- **Type consistency:** `plan_promotion`, `PromotionPlan`, `AliasMove/MissingBinding/Blocked`, `render_pr_body(plan, version)`, `pr_labels(plan)`, `stub_binding(model, alias)`, `bump_nebula_pin(text, version)`, `STUB_ENDPOINT` used identically across T1→T3.
- **No placeholders:** every code/test step is complete.
