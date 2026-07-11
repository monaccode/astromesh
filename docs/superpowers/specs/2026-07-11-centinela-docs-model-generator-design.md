# Centinela Docs — Model Card Generator (sub-project 3)

**Date:** 2026-07-11
**Repo:** astromesh (docs-site)
**Status:** Approved design — ready for implementation plan
**Part of:** Centinela MLOps effort (sub-project 3 of 4). Sub-projects 1–2 shipped
(foundry catalog + scout in nebula; runtime reconciler + provider in astromesh).

## Purpose

Generate model documentation pages for the Astromesh docs site directly from the
foundry's machine contract (`catalog.lock.json`). The catalog is the single source
of truth for what models exist, their contracts, revisions, and eval results. The
docs site should reflect that contract automatically — no hand-authored model pages
that drift from the lock.

Scope: one Node generator + a vendored copy of the lock + a "Models" sidebar section,
all inside `docs-site/`. No changes to runtime, provider, or the nebula repo.

## Context / Code reality

- **`docs-site/`** is an Astro Starlight site in the **astromesh** repo. Content lives
  in `src/content/docs/**` (`.mdx`). The sidebar is hand-authored in `astro.config.mjs`.
  Starlight supports `autogenerate: { directory: '<dir>' }` for a sidebar group.
- **`catalog.lock.json`** lives in the **nebula** repo
  (`astromesh-nebula/nebula/catalog.lock.json`), compiled from `catalog/*.yaml`. It is
  a small, flat JSON: `{ schema_version, models: [ { name, kind, task, vertical,
  hf_repo, contract{labels,validation}, aliases{<alias>:<rev>},
  revisions{<rev>:{base_model, dataset, gate, train_config_hash, formats, sha,
  eval{macro_f1, invalid_rate}, version}} } ] }`.
- The lock today carries **placeholders** (`REPLACE_WITH_REAL_HF_REVISION_SHA`,
  `sha256:REPLACE_WITH_REAL_TRAIN_CONFIG_HASH`) and `eval` values of `0.0` because the
  first model is not yet trained/published.
- **Docs deploy** (`.github/workflows/docs.yml`) is **Node-only**: a single checkout
  (astromesh), `npm ci` + `npm run build` in `docs-site`. It does **not** install
  Python, the nebula wheel, or check out the nebula repo. It triggers on push to
  `develop` touching `docs-site/**` or `docs/**`.
- `docs-site` currently has **no test tooling and no test deps**. The generator will
  use only Node built-ins (`fs`, `path`, `node:test`) — zero new dependencies.

## Fixed decisions (from brainstorming)

1. **Lock source = vendored copy + sync script.** A committed copy of the lock lives in
   astromesh; a sync script refreshes it from the sibling nebula checkout. The docs
   build stays hermetic (Node-only, offline, deterministic). Staleness-vs-nebula
   guarding is deferred to the sub-project 4 PR bots.
2. **Generated MDX = build-time, gitignored.** `gen:models` runs in `prebuild`/`predev`;
   the MDX under `src/content/docs/models/` is a pure derivative, never committed. The
   vendored lock JSON is the only committed source on the docs side.
3. **Card depth = Rich.** Full metadata, contract, aliases, per-revision detail
   (base_model, dataset, train_config_hash, formats, sha), serving notes, a "How to use"
   snippet, plus a Models index page with a table grouped by vertical.
4. **Preview vs released status** is derived from the lock so today's placeholder lock
   renders honestly (see §4).

## 1. Architecture / data flow

```
nebula/catalog.lock.json
   │  (sync-catalog.mjs — run locally now, by the sub-project 4 bot later)
   ▼
docs-site/src/data/catalog.lock.json          (vendored, COMMITTED — single docs-side source)
   │  (gen-models.mjs — npm prebuild/predev)
   ▼
docs-site/src/content/docs/models/*.mdx       (GITIGNORED — pure derivative)
   │  (astro build)
   ▼
GitHub Pages
```

The nebula lock is the ultimate source of truth. The vendored copy is the only committed
docs-side artifact; MDX is regenerated on every build. `docs.yml` is **not** modified —
it already runs `npm run build`, which triggers the `prebuild` hook.

## 2. Components

Each unit has one responsibility and a well-defined interface.

### 2.1 `docs-site/scripts/sync-catalog.mjs`
- **Does:** copies `../astromesh-nebula/nebula/catalog.lock.json` →
  `docs-site/src/data/catalog.lock.json`.
- **Validates (dependency-free):** the source parses as JSON, `schema_version` is a
  supported value (`"1"`), and `models` is an array. Fails loudly otherwise (non-zero
  exit, clear message naming the expected source path).
- **Source path:** resolved relative to the astromesh repo root; overridable via a
  positional arg / env for non-standard checkout layouts.
- **Interface:** `validateLock(obj) -> void (throws)` exported for unit tests; a thin
  main() does the fs read/copy.
- **Usage:** manual/local now (`npm run sync:catalog`); automated by the sub-project 4
  bot later.

### 2.2 `docs-site/scripts/gen-models.mjs`
Split into a pure render core and a thin I/O wrapper:
- **Pure:** `renderModels(lock) -> { cards: [{ slug, mdx }], index: { mdx } }`. No I/O.
  Deterministic. This is what the unit tests exercise.
- **Wrapper:** reads `src/data/catalog.lock.json`, calls `renderModels`, **cleans**
  `src/content/docs/models/` and writes `index.mdx` + one `<slug>.mdx` per model. The
  clean-then-write makes it idempotent (a removed model leaves no stale page).
- **Slug:** the model `name` (already kebab-ish, e.g. `centinela-sentiment`).

### 2.3 `astro.config.mjs`
- Add a top-level sidebar group **"Models"** using
  `{ label: 'Models', autogenerate: { directory: 'models' } }`, placed **after the
  "Reference" group**. This is a single static edit; the generator never touches the
  config. Autogenerate reads the `models/` directory at build time (files exist because
  `prebuild` ran first).

### 2.4 `docs-site/package.json` scripts
- `"gen:models": "node scripts/gen-models.mjs"`
- `"prebuild": "npm run gen:models"`  (npm runs this automatically before `build`)
- `"predev": "npm run gen:models"`    (so `astro dev` also has fresh pages)
- `"sync:catalog": "node scripts/sync-catalog.mjs"`
- `"test": "node --test scripts/"`

### 2.5 `docs-site/.gitignore`
- `src/content/docs/models/`

## 3. Card content (Rich)

Per model → `models/<name>.mdx` (Starlight frontmatter `title`, `description`):

- **H1** = model `name`; a **status badge** (`released` / `preview`, see §4).
- **Metadata badges:** `vertical`, `task`, `kind`, `gate` (of the referenced revision).
- **HF link:** `https://huggingface.co/<hf_repo>`.
- **Contract:** `labels` (rendered as a list/inline), `validation`.
- **Aliases:** table alias → revision (e.g. `prod → v0.1`).
- **Revisions:** table — version, base_model, dataset, gate, macro_f1, invalid_rate.
- **Per-revision detail** (one block per revision): base_model, dataset,
  train_config_hash, formats, sha (rendered verbatim; placeholders shown as-is).
- **Serving:** note that serving is generative via TGI `/v1/chat/completions`
  (OpenAI-compatible), so per-label probability is unavailable → provider
  `SentimentResult.score = None`.
- **How to use:** a short snippet showing (a) a `bindings.yaml` alias→endpoint binding
  and (b) provider usage — typed `classify()` returning `SentimentResult` and/or the
  routable `CentinelaProvider`. Illustrative, matching sub-project 2's shipped API.

`models/index.mdx`: a landing page with a table of **all** models **grouped by
vertical**, each row: model (link), task, kind, status.

## 4. Preview vs released status

Derived per model from its **primary revision**, resolved without guessing at
revision ordering (the lexicographic-vs-recency ordering is an unresolved Centinela
backlog item and must not be reintroduced here):

- primary = the revision pointed to by the `prod` alias, if present;
- else, if the model has exactly one revision, that revision;
- else (multiple revisions, no `prod` alias) the primary is **undefined by design** —
  the generator marks the model **preview** and does not pick a "latest".

Given a resolved primary revision:

- **released** iff its `gate == "passed"` **and** its `sha` matches
  `/^[0-9a-f]{7,40}$/` (a real HF revision SHA).
- **preview** otherwise (today's lock: `sha` is `REPLACE_WITH_REAL_HF_REVISION_SHA`).

A **preview** card/row shows a banner: "Preliminary — this model is defined in the
catalog but not yet published." This keeps the placeholder lock rendering honestly
instead of implying the model is live.

## 5. Errors / edge cases

- **Empty catalog / no `models`:** the index renders "No published models yet" and no
  cards are written. The build does not fail.
- **Unsupported `schema_version`:** `gen-models` throws loudly (fails the build) rather
  than emitting garbage. Supported: `"1"`.
- **`sync-catalog` with no sibling nebula checkout:** clear error naming the expected
  path and how to override it. It never writes a partial/invalid vendored file.
- **Missing revision referenced by an alias:** treated as a malformed lock — throw with
  the offending alias/revision named (the lock is machine-produced; this signals a bug
  upstream, not a normal state).

## 6. Testing (node:test, zero new deps)

`docs-site/scripts/gen-models.test.mjs` (against in-memory fixture locks):
- Rich card renders all sections from a fixture: contract labels, aliases row, revisions
  row with eval, per-revision detail (train_config_hash, formats, sha), HF link, serving
  note, "How to use" snippet.
- Status: `preview` when `sha` is a placeholder; `released` when `sha` is a real
  40-hex and gate passed.
- Index: grouped-by-vertical table contains the model row with correct status.
- Empty catalog → index says "no published models", zero card entries.
- Unsupported `schema_version` → throws.
- Malformed alias→revision → throws with the name.

`docs-site/scripts/sync-catalog.test.mjs`:
- `validateLock` accepts a well-formed lock; rejects non-JSON, missing `models`, and
  unsupported `schema_version`.

Integration check: `astro build` succeeds with the generated pages (covered by the
existing docs.yml on merge; run locally during implementation).

## 7. Out of scope (deferred)

- Staleness guard comparing the vendored lock against nebula's (→ sub-project 4 PR bots).
- Live HF Inference Endpoint provisioning (separate infra sub-project).
- Populating real eval numbers / real SHAs — those arrive when the first Centinela model
  is actually trained and published; the generator already renders them honestly via the
  preview/released status.
- Any change to the nebula repo, the runtime, or the provider.

## File manifest

New:
- `docs-site/scripts/sync-catalog.mjs`
- `docs-site/scripts/gen-models.mjs`
- `docs-site/scripts/gen-models.test.mjs`
- `docs-site/scripts/sync-catalog.test.mjs`
- `docs-site/src/data/catalog.lock.json` (vendored, committed)

Modified:
- `docs-site/astro.config.mjs` (add "Models" sidebar group)
- `docs-site/package.json` (scripts: gen:models, prebuild, predev, sync:catalog, test)
- `docs-site/.gitignore` (ignore generated `models/` dir)

Generated (gitignored, not committed):
- `docs-site/src/content/docs/models/index.mdx`
- `docs-site/src/content/docs/models/<name>.mdx`
