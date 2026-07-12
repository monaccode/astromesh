# Centinela Promotion Bot — cross-repo lock sync + bindings promotion (sub-project 4)

**Date:** 2026-07-12
**Repos:** astromesh (bot + planner) · astromesh-nebula (dispatch trigger)
**Status:** Approved design — ready for implementation plan
**Part of:** Centinela MLOps effort (sub-project 4 of 4). Sub-projects 1–3 shipped
(foundry catalog + scout in nebula; runtime reconciler + provider in astromesh;
docs model-card generator in astromesh).

## Purpose

Automate GitOps steps 6 and 9 of the Centinela MLOps flow (master spec
`2026-07-10-centinela-mlops-design.md` §3): when the nebula foundry publishes a new
`catalog.lock.json` (an alias moved to a new revision), open a pull request in astromesh
that syncs the lock across its consumers and summarizes the promotion for a human to
merge. Steps 6 (staging) and 9 (prod) are the **same machinery** — they differ only in
which alias moved. The prod release gate stays human and lives entirely in nebula (a
human moves the `prod` alias there); this bot only reacts to the resulting lock change.

Scope now: the cross-repo detection + PR machinery, working end-to-end **in dry form**
(no live HF endpoints yet — the bot emits endpoint stubs for a human to fill). This also
closes the staleness guard deferred from sub-project 3 (the vendored docs lock becomes
bot-refreshed instead of hand-maintained).

## Context / code reality

- **How astromesh consumes the lock (two consumers):**
  1. **Runtime:** the reconcile CLI reads the lock from the installed nebula wheel —
     `astromesh-node/.../cli/commands/centinela.py::_load_lock()` does
     `files("nebula") / "catalog.lock.json"`. So the runtime's view of the lock is pinned
     by the `astromesh-nebula` dependency version.
  2. **Docs:** a vendored committed copy at `docs-site/src/data/catalog.lock.json`
     (sub-project 3), refreshed by `docs-site/scripts/sync-catalog.mjs`.
- **`bindings.yaml`** (`config/centinela/bindings.yaml`) maps `{model, alias, endpoint}` —
  the alias name (`staging`/`prod`) and endpoint URL are **stable**. When an alias moves to
  a new revision, the alias→revision mapping changes in the *lock*, not in bindings.yaml.
  So a promotion normally does **not** edit bindings.yaml; it refreshes the lock (docs copy
  + dep pin). bindings.yaml is edited **only** when a served alias appears that has no
  binding yet (a new endpoint is needed).
- **The reconciler** (`astromesh/centinela/reconcile.py`) already encodes what "served"
  means: `_SERVED_KINDS = {"classifier", "extractor"}` and the rule that only a revision
  with `gate == "passed"` may be served. The promotion planner reuses these.
- **Lock is not yet workflow-published in nebula:** no workflow commits the lock or fires a
  dispatch today (the lock is committed by hand / by the training pipeline's PR). This
  sub-project adds the nebula-side dispatch trigger.
- **Cross-repo token:** nebula already holds a `GH_PIPELINE_TOKEN` secret (used by
  `release.yml`); the dispatch reuses it (or a dedicated fine-grained PAT / GitHub App with
  `contents:write` + `pull-requests:write` on astromesh).
- **Reality check:** no model is trained yet, so today's lock carries placeholders
  (`REPLACE_WITH_REAL_HF_REVISION_SHA`, eval `0.0`). The bot must render honestly against
  placeholder data and never fabricate endpoints or SHAs.

## Fixed decisions (from brainstorming)

1. **Scope = sync + bindings promotion** (full steps 6 and 9), working in dry form until
   live endpoints exist.
2. **Trigger = nebula pushes** via `repository_dispatch` (event `catalog-lock-updated`).
   Reactive and immediate; the payload carries `{ref, version, sha}` and astromesh **fetches
   the lock at that ref** (auditable; decouples payload from lock content).
3. **Missing binding for a served alias → stub + human checklist.** The PR adds a stub
   binding with `REPLACE_WITH_REAL_HF_ENDPOINT` and a checklist item; the bot never invents
   an endpoint.
4. **`blocked` promotions still open a PR** with a prominent warning and a failing check
   (visible/auditable), rather than silently opening nothing.
5. **staging vs prod = same code path**, differentiated only by a PR label
   (`centinela:staging` / `centinela:prod`) and body emphasis. Prod stays human-gated in
   nebula; both astromesh PRs are human-merged (no auto-merge).

## 1. Architecture / data flow

```
nebula: push to develop/main touching nebula/catalog.lock.json
  └─ .github/workflows/notify-catalog.yml
       → repository_dispatch(event_type: "catalog-lock-updated",
          client_payload: { ref, version, sha })         [token: GH_PIPELINE_TOKEN]
                     │
                     ▼
astromesh: .github/workflows/centinela-sync.yml           (on: repository_dispatch)
  1. checkout astromesh
  2. fetch the new lock from nebula at client_payload.ref → new_lock.json
  3. astromeshctl centinela plan-promotion \
        --new-lock new_lock.json --version <payload.version> --pr-body pr-body.md
       · plan_promotion(old_lock, new_lock, bindings)     (PURE, unit-tested)
       · apply edits: refresh docs-site/src/data/catalog.lock.json,
         bump the astromesh-nebula pin, add a stub binding if a served alias lacks one
       · write the PR body (promotion summary + human checklist) to pr-body.md
       · exit non-zero only signals `blocked` to the workflow (which still opens the PR)
  4. peter-evans/create-pull-request on stable branch bot/centinela-sync
       (label centinela:staging | centinela:prod; failing check if blocked)
```

**Baseline of the diff:** the currently-vendored `docs-site/src/data/catalog.lock.json` is
the "old" lock; the "new" lock is fetched from nebula at the dispatched ref. A stable branch
`bot/centinela-sync` means repeated dispatches update one PR instead of spamming new ones.

## 2. Components

Each unit has one responsibility and a well-defined interface.

### 2.1 `astromesh/centinela/promote.py` — pure planner (no I/O)

Sits next to `reconcile.py`; imports the reconciler's serve rules (`_SERVED_KINDS`, the
`gate == "passed"` check) so "served" means the same thing everywhere.

- **`plan_promotion(old_lock: dict, new_lock: dict, bindings: dict) -> PromotionPlan`** —
  deterministic, no I/O. Compares the two locks and the operator's bindings.
- **`PromotionPlan`** (dataclass / pydantic BaseModel):
  - `alias_moves: list[AliasMove]` — each `{model, alias, from_rev, to_rev, from_eval,
    to_eval}` for an alias whose target revision changed (or a newly-added alias).
  - `missing_bindings: list[MissingBinding]` — `{model, alias}` for a **served** alias
    (kind in `_SERVED_KINDS`, target gate `passed`) that has no binding in bindings.yaml.
  - `blocked: list[Blocked]` — `{model, alias, reason}` for an alias that **has** a binding
    but now points at a `gate != "passed"` revision or a revision missing from the new lock.
  - `is_noop: bool` — true iff no moves, no missing bindings, no blocks (locks equivalent).
- **`render_pr_body(plan: PromotionPlan, version: str) -> str`** — Markdown: a promotion
  summary table (model, alias, from→to, macro_f1 Δ, invalid_rate Δ, sha), a
  `- [ ]` checklist for each missing binding ("provide the live endpoint URL for
  `<model>/<alias>` before merge"), and a prominent ⚠️ section listing any `blocked` items.
  Prod moves get a louder heading.
- **`stub_binding(model: str, alias: str) -> dict`** — a `{model, alias, endpoint}` entry
  with `endpoint = "https://REPLACE_WITH_REAL_HF_ENDPOINT.endpoints.huggingface.cloud"`.
- **`pr_labels(plan) -> list[str]`** — `["centinela:prod"]` if any prod alias moved, else
  `["centinela:staging"]` (plus `centinela:blocked` when `blocked` is non-empty).

`from_eval`/`to_eval` read `revisions[<rev>].eval.{macro_f1, invalid_rate}` (placeholders
render as-is; a missing old revision renders `from` as `—`).

### 2.2 `astromesh-node` CLI: `astromeshctl centinela plan-promotion`

Thin wrapper mirroring the existing `reconcile` command:

- Options: `--new-lock <path>` (required), `--version <str>` (the nebula version to pin),
  `--bindings <path>` (default `./config/centinela/bindings.yaml`),
  `--vendored-lock <path>` (default `./docs-site/src/data/catalog.lock.json`, the baseline),
  `--pr-body <path>` (default `./pr-body.md`).
- Reads baseline vendored lock + new lock + bindings; calls `plan_promotion`.
- **Applies file edits:**
  - overwrite the vendored lock with the new lock (byte-for-byte from the fetched file);
  - bump the `astromesh-nebula` pin to `>= <version>` in the relevant `pyproject.toml`(s);
  - for each `missing_bindings` entry, append a `stub_binding` to bindings.yaml.
- Writes `render_pr_body(...)` to `--pr-body`.
- Prints a one-line summary. Exit code: `0` normally; **non-zero when `blocked` is
  non-empty** (the workflow treats this as "open the PR but mark the check failed").
  `is_noop` prints "no changes" and exits `0` without editing (the workflow then skips the PR).

### 2.3 `.github/workflows/centinela-sync.yml` (astromesh)

- `on: repository_dispatch: types: [catalog-lock-updated]`.
- Steps: checkout → set up Python/uv → `uv sync` → fetch the new lock from nebula at
  `client_payload.ref` (raw githubusercontent with a read token, or `actions/checkout` of
  nebula at the ref) → run `astromeshctl centinela plan-promotion` → if it reported "no
  changes", stop → else `peter-evans/create-pull-request@v6` on `bot/centinela-sync` with the
  generated body, computed labels, and a failing status when `blocked`.
- The PR is never auto-merged.

### 2.4 `.github/workflows/notify-catalog.yml` (nebula)

- `on: push: branches: [develop, main], paths: [nebula/catalog.lock.json]`.
- Single step: `POST /repos/<org>/astromesh/dispatches` with
  `event_type: catalog-lock-updated` and `client_payload: {ref: <sha>, version: <nebula
  version>, sha: <sha>}`, authenticated with `GH_PIPELINE_TOKEN` (or a dedicated
  fine-grained token). `version` is read from nebula's `pyproject.toml`.

## 3. Handling the no-live-endpoint reality

- **alias moved, binding exists** → refresh vendored lock + bump pin; PR body summarizes the
  eval delta and sha. No bindings.yaml change.
- **served alias, no binding** → append a stub binding + a checklist item; human fills the
  URL before merge. *(fixed decision 3)*
- **bound alias now at `gate != passed` or revision removed** → `blocked`; CLI exits
  non-zero; the workflow still opens the PR with a ⚠️ warning and a failing check. *(4)*
- **no change** → CLI reports noop; workflow opens no PR.

## 4. Errors / edge cases

- **Unsupported `schema_version` in the new lock** → planner throws loudly (fail the run)
  rather than emit a garbage PR. Supported: `"1"` (matches sub-projects 2–3).
- **New lock unfetchable** (bad ref / network) → the workflow fails before planning; no PR.
- **A model removed entirely from the new lock while still bound** → surfaced as `blocked`
  (its bound alias no longer resolves).
- **Empty `models` in the new lock** → planner treats every existing binding as `blocked`
  (nothing is served); PR warns. It does not delete bindings.
- **Placeholder eval / sha** (today's reality) → rendered verbatim in the summary; the diff
  still detects an alias→revision change even with placeholder shas, because the *revision
  key* (e.g. `v0.1`) is what the alias points at.

## 5. Testing (pytest for the planner; thin workflows validated by dry run)

`tests/test_centinela_promote.py` against in-memory fixture locks:
- staging alias moved, binding present → `alias_moves` has 1, no missing/blocked, not noop.
- prod alias moved → `pr_labels` includes `centinela:prod`.
- new served alias, no binding → `missing_bindings` has 1; `stub_binding` shape correct.
- bound alias whose new target has `gate != "passed"` → `blocked` has 1.
- revision removed under a bound alias → `blocked` has 1.
- identical locks → `is_noop` is true.
- non-served kind (e.g. `instruct`) alias with no binding → **not** flagged missing.
- unsupported `schema_version` → raises.
- `render_pr_body` includes the eval deltas and a `- [ ]` checklist line per missing binding.

CLI + workflows: a dry-run job runs `plan-promotion` against a fixture new lock and asserts
the edits + PR body are produced; the actual `create-pull-request` / dispatch steps are
exercised on merge (guarded so a fork/PR can't fire cross-repo dispatch).

## 6. Out of scope (deferred)

- Live HF Inference Endpoint provisioning (separate infra sub-project) — the bot emits
  endpoint stubs; it never creates or scales endpoints.
- Auto-merge of the promotion PR — both staging and prod PRs are human-merged.
- The nebula-side "catalog: `<model>` `<rc>`" PR (master spec step 4) — created by the
  training pipeline, not this bot.
- Resolving revision ordering (lexicographic vs recency) — still deferred; the bot keys off
  explicit alias targets, never "latest".

## File manifest

New (astromesh):
- `astromesh/centinela/promote.py` (pure planner)
- `tests/test_centinela_promote.py`
- `astromesh-node/src/astromesh_node/cli/commands/centinela.py` → add `plan-promotion`
  command (extend the existing file)
- `.github/workflows/centinela-sync.yml`

New (astromesh-nebula):
- `.github/workflows/notify-catalog.yml`

Modified (astromesh, by the bot at runtime — not committed by this sub-project):
- `docs-site/src/data/catalog.lock.json` (refreshed)
- `config/centinela/bindings.yaml` (stub appended when a served alias lacks a binding)
- `pyproject.toml` / `astromesh-node/pyproject.toml` (`astromesh-nebula` pin bumped)
