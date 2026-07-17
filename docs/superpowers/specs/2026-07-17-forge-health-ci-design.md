# Astromesh Forge — Health & CI Gate

**Date:** 2026-07-17
**Status:** approved, ready for implementation planning
**Scope:** `astromesh-forge/`, `.github/workflows/ci.yml`, root `CHANGELOG.md`

## Goal

Leave Forge maintained and gated, without touching features. `test-forge` in CI must fail a PR that
breaks the build, the tests, or the lint — so Forge cannot silently rot again. This is the
prerequisite for any later feature work, not a substitute for it.

## Why now

Forge has been dormant since **2026-03-30** (`ba9cd0c`, its `v0.23.0` release): zero commits in three
and a half months while the core went from 0.23.0 to 0.34.0.

The assumption worth killing first: **Forge is not broken.** Measured on 2026-07-17, at
`ba9cd0c`'s tree, with the exact dependencies its lockfile pins:

| Check | Result |
|---|---|
| `tsc -b && vite build` | green — 1976 modules, 272 ms |
| `vitest run` | green — **20/20 tests across 5 files** |
| `eslint .` | **red — 18 errors, 2 warnings** |
| `npm test` | **does not exist** — no `test` script |
| CI | **no workflow references `astromesh-forge` at all** |
| `package-lock.json` | clean; installed versions match the lockfile exactly |

So Forge is dormant, not rotten. The lint has been red **since at least 2026-03-30**: the lockfile
pins `eslint-plugin-react-hooks` **7.0.1** — the same version that reports the errors today — and
`eslint.config.js` extends its `flat.recommended` preset. The errors were committed, not inherited
from a later dependency bump. Nothing caught them because nothing looks.

This is the third instance of one pattern in this codebase: the Orbit suite sat red until
`test-orbit` was added; the OS image's "≤ 500 MB" budget was documented but ungated (and had drifted
to 379 MB); Forge builds and tests green but nothing runs them. **A claim without a gate is
decoration.** This spec adds the gate.

## Design principle

The gate can only demand what is already green, so the lint must go green in this same spec — and
the one thing this spec must not do is change React runtime behaviour in components that have no
test coverage. That would be making the risky change precisely while the safety net is still absent.

Hence the split that drives every decision below:

> **Fix what TypeScript or the existing tests can prove safe. Document what changes React runtime
> behaviour in an untested component, and defer it to its own spec — with the net in place.**

## Current lint inventory (authoritative, `eslint . --format json`, 2026-07-17)

**Group A — fix for real (4).** Compile-time-verifiable: `tsc -b` and the existing 20 tests prove
these introduce no behaviour change.

| File:line | Rule |
|---|---|
| `src/utils/pipeline-graph.ts:48` | `prefer-const` |
| `src/components/wizard/StepModel.tsx:159` | `@typescript-eslint/no-unused-vars` |
| `src/api/__tests__/client.test.ts:43` | `@typescript-eslint/no-explicit-any` |
| `src/components/console/ConsoleRightPanel.tsx:18` | `react-refresh/only-export-components` |

`only-export-components` needs no module move: `findSpanInTree` has no importer outside its own file
(it is used at `ConsoleRightPanel.tsx:21` and `:111` only), so dropping the `export` keyword settles
it, and `tsc -b` proves nothing else wanted it.

All four fixes were verified together before this spec was finalised: applied, then
`tsc -b && vite build` green and 20/20 tests passing, and `eslint . --format json` reporting exactly
16 problems instead of 20 — the four above gone, Group B untouched. Then reverted, leaving the work
to implementation.

**Group B — disable with a written justification (16).** Each of these changes what React does at
runtime. All sit in components with no test coverage (`PipelinePropertiesPanel`, `Toolbox`,
`ConsoleRightPanel`, `ConsoleShell`, `SpanNode`, `TemplateGallery`, `TemplatePreview`, `StepTools` —
the only component test is `App.test.tsx`).

| File:line | Rule |
|---|---|
| `PipelinePropertiesPanel.tsx:107,157,242,316,411` | `react-hooks/set-state-in-effect` (5) |
| `Toolbox.tsx:102,112` | `react-hooks/set-state-in-effect` (2) |
| `ConsoleRightPanel.tsx:68` | `react-hooks/set-state-in-effect` |
| `ConsoleShell.tsx:44` | `react-hooks/set-state-in-effect` |
| `TemplateGallery.tsx:33` | `react-hooks/set-state-in-effect` |
| `TemplatePreview.tsx:44` | `react-hooks/set-state-in-effect` |
| `StepTools.tsx:145` | `react-hooks/set-state-in-effect` |
| `ConsoleRightPanel.tsx:71,130` | `react-hooks/exhaustive-deps` (2, warnings) |
| `ConsoleRightPanel.tsx:121` | `react-hooks/preserve-manual-memoization` |
| `SpanNode.tsx:104` | `react-hooks/static-components` |

The 12 `set-state-in-effect` violations are two honest patterns that the React-Compiler-era rules
flag: syncing props into local form state (`PipelinePropertiesPanel`, `TemplatePreview`,
`StepTools`) and fetching in an effect (`Toolbox`'s `.then(setAgents)` / `.then(setBuiltinTools)`).
Both work. Both have an idiomatic replacement (remount via `key`, derive during render, move
fetching out of the effect). Neither is safe to change blind.

`exhaustive-deps` is included here, not in Group A, for the same reason: adding a missing dependency
can turn a stable effect into a render loop, and nothing in this repo would catch it.

## What gets built

Five independent units.

### 1. `test` script

`astromesh-forge/package.json` gains `"test": "vitest run"`. Forge already has `vitest@4.1.0`,
`jsdom@29.0.1` and 5 passing test files — with no npm entry point to run them. This is the piece
that makes the gate possible.

### 2. Group A fixes

The four fixes above. Verified by `tsc -b` plus the existing suite.

### 3. Group B disables

An `// eslint-disable-next-line <rule>` on each of the 16 sites, each with a one-line reason naming
the pattern and the idiomatic fix being deferred. Rationale: the debt becomes greppable
(`grep -rn "eslint-disable-next-line react-hooks" src/`) and each site carries its own argument,
rather than one blanket rule-off in `eslint.config.js` that would also hide *new* violations.

The rules stay enabled in config. A new `set-state-in-effect` anywhere else fails the gate.

### 4. `test-forge` CI job

A new job in `.github/workflows/ci.yml`, mirroring the shape of its siblings (`test`, `test-node`,
`test-cli`, `test-orbit`): checkout → `actions/setup-node` (with npm cache) → `npm ci` → lint → test
→ build, all with `working-directory: astromesh-forge`.

One deliberate departure from the sibling jobs: **`--max-warnings 0`**. `eslint` exits 0 on warnings
by default, which would let warnings accumulate invisibly — the exact failure mode this spec exists
to end. With Group B's warnings explicitly disabled, zero-warnings is achievable today, so the gate
demands it.

`npm ci` (not `npm install`) — the lockfile is clean and must stay authoritative.

**No path filter.** An earlier draft of this spec had the job run only on `astromesh-forge/**`
changes. Dropped: GitHub Actions has no native per-job path filter, and both ways of getting one
cost more than the roughly one minute of CI they save — a third-party action (`dorny/paths-filter`)
would put an external dependency in the build chain, and a separate workflow file would break the
single-`CI`-badge convention the README links to. `test-forge` runs on every push, exactly like its
four siblings. If it ever gets slow enough to matter, moving it to its own workflow with a native
`on.push.paths` filter is the cheap fix.

### 5. Version + changelog

`astromesh-forge/package.json` → **0.24.0**, following its own line (`adk` is at 0.2.0, `orbit` at
0.4.0, `node`/`cli` at 0.1.1 — every sub-package versions independently; nothing is in sync with the
core's 0.34.0). Forge changes in this spec, so it earns a bump. Forge is `"private": true` and is
never published to npm, so the number is an internal label, not a contract.

A root `CHANGELOG.md` entry under `### Changed (Astromesh Forge)`.

## The Node version

The build and tests were verified green on **Node 20.20.2** local. Node 20 reached end of life in
April 2026; Node 22 is the active LTS. `package.json` declares no `engines` field, so nothing pins
this today — which is why the choice has to be made here rather than left to whatever the runner
happens to ship.

The installed toolchain declares (read from `node_modules`, not assumed):

- `vite@8.0.1` → `node: ^20.19.0 || >=22.12.0`
- `vitest@4.1.0` → `node: ^20.0.0 || ^22.0.0 || >=24.0.0`

**Node 22.12+ satisfies both**, so that is what `test-forge` pins and what `package.json` declares
as `"engines": { "node": ">=22.12" }`. Local Node 20.20.2 also satisfies both, which is why today's
green run is not evidence either way.

Supporting evidence: `.github/workflows/docs.yml` already builds `docs-site` — Astro, i.e. Vite — on
`node-version: 22` in this repo's CI, so Node 22 with a Vite toolchain is a proven combination here,
not a bet.

Engine ranges are a declaration of intent, not a guarantee, so the implementation's first step still
runs `npm ci && npm run lint && npm test && npm run build` on Node 22 and confirms it green before
the job is written. If it is not, the job pins Node 20 and the Node 22 migration is recorded as an
explicit follow-up rather than silently deferred.

## Testing

The gate is the deliverable, so the acceptance criterion is behavioural, not just "CI is green":

1. `npm run lint`, `npm test`, `npm run build` all green locally and in CI.
2. **The gate must be proven to bite.** Temporarily introduce a violation of each gated dimension —
   a failing assertion, a type error, a fresh `set-state-in-effect` — and confirm `test-forge` goes
   red for each, then revert. A gate observed only passing is not a verified gate: this session
   shipped a workflow whose `build-deb`/`build-image` were green while the image did not boot, and
   an image-size claim that no job ever evaluated.
3. The existing 20 tests must still pass unchanged. This spec adds no test coverage — Group B's
   components stay uncovered, deliberately, and that is what makes the deferral honest.

## Out of scope

- **The hook refactor.** Group B's 16 sites get their own spec, once the gate exists. Doing it here
  would mean changing untested runtime behaviour with no net — the thing this spec is built to
  prevent.
- **Feature parity with the core.** The core mounts 14 routers; Forge consumes 5 (`agents`,
  `templates`, `tools/builtin`, `traces`, `health`). It knows nothing of the WebSocket live run
  events (v0.34.0), workflows and HITL approvals (v0.31/0.32), RAG pipeline CRUD, dynamic blueprint
  registration, per-role model routing (v0.29.0), or the `memory`/`mesh`/`metrics`/`dashboard`/
  `system` routers. That is several independent subsystems and needs decomposing into one spec per
  area — not this one.
- **Deploying Forge.** Orbit deploys only the `runtime` Cloud Run service; Studio and cloud-api were
  removed deliberately in `6278ccc`. This spec does not reintroduce them.
- **Adding component test coverage.** Worth doing, and the natural companion to the hook refactor,
  but not required to stand the gate up.

## Success criteria

- A PR that breaks Forge's build, tests, or lint goes red, and this is demonstrated, not assumed.
- `astromesh-forge` is at 0.24.0 with a changelog entry.
- Forge's deferred debt is greppable, each site carrying its own justification.
- No React runtime behaviour changed in this spec.
