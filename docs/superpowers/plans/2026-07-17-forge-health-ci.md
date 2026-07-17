# Forge — Health & CI Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a `test-forge` CI job that fails any PR breaking Forge's build, tests, or lint — so Forge cannot silently rot again.

**Architecture:** No new architecture; this is a gate. The gate can only demand what is already green, so the lint goes green first (Tasks 1–2), then the gate is added and proven to bite (Task 3). Forge already builds green and passes 20/20 tests today — those need only an npm entry point, not repair.

**Tech Stack:** React 19 + Vite 8 + TypeScript 5.9, vitest 4 + jsdom 29, ESLint 9 + eslint-plugin-react-hooks 7, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-07-17-forge-health-ci-design.md`

## Global Constraints

- **Never change React runtime behaviour in this plan.** Fix only what `tsc -b` or the existing 20 tests can prove safe; everything else gets a documented `eslint-disable`. Group B's components have no test coverage — the only component test is `App.test.tsx`.
- All work happens in `astromesh-forge/` except Task 3 (`.github/workflows/ci.yml`) and Task 4 (root `CHANGELOG.md`).
- Forge version becomes **0.24.0** — its own line, not the core's 0.34.0. Forge is `"private": true` and never published to npm.
- Use `npm ci`, never `npm install`: `package-lock.json` is clean and authoritative. Do not let it drift.
- The existing 20 tests must still pass, unchanged, at every commit.
- Lint gate runs with `--max-warnings 0`. Zero warnings is achievable once Task 2 lands.
- Never use `eslint-disable` without a written one-line reason naming the deferred idiomatic fix.
- Baseline to preserve: `eslint . --format json` reports exactly **20 problems (18 errors + 2 warnings)** before Task 1.

---

### Task 1: The four provable lint fixes

Removes exactly 4 of the 20 lint problems. Each is verified by `tsc -b` plus the existing suite — no runtime behaviour changes. All four were validated together before this plan was written: build green, 20/20 tests, lint down to exactly 16.

**Files:**
- Modify: `astromesh-forge/src/utils/pipeline-graph.ts:48`
- Modify: `astromesh-forge/src/components/console/ConsoleRightPanel.tsx:18`
- Modify: `astromesh-forge/src/api/__tests__/client.test.ts:2,43`
- Modify: `astromesh-forge/eslint.config.js`

**Interfaces:**
- Consumes: nothing.
- Produces: a tree where `eslint . --format json` reports exactly 16 problems (14 errors + 2 warnings), all `react-hooks/*`. Task 2 disables those 16.

- [ ] **Step 1: Install dependencies and record the baseline**

```bash
cd astromesh-forge
npm ci
npx eslint . --format json 2>/dev/null | python3 -c "
import sys,json; d=json.load(sys.stdin)
n=sum(len(f['messages']) for f in d)
e=sum(1 for f in d for m in f['messages'] if m['severity']==2)
print(f'{n} problems: {e} errors + {n-e} warnings')
"
```

Expected: `20 problems: 18 errors + 2 warnings`. If this differs, stop and report — the plan's baseline no longer holds.

- [ ] **Step 2: Fix `prefer-const`**

`pipeline-graph.ts:48` — `nextEdges` is mutated with `.push()` but never reassigned, so `const` is correct.

```ts
  const nextEdges = edges.filter((e) => e.source !== nodeId && e.target !== nodeId);
```

- [ ] **Step 3: Fix `react-refresh/only-export-components`**

`ConsoleRightPanel.tsx:18` — `findSpanInTree` is used only inside this file (lines 21 and 111) and has no importer anywhere else, so drop the `export`. Do not move it to another module; `tsc -b` in Step 6 proves nothing external wanted it.

```ts
function findSpanInTree(nodes: SpanTreeNode[], id: string): SpanTreeNode | null {
```

- [ ] **Step 4: Fix `@typescript-eslint/no-explicit-any`**

`client.test.ts` — the stub config is cast to `any`. `createAgent(config: AgentConfig)` is the real signature, so cast to the real type instead. The test only asserts the outgoing fetch shape, so the stub stays intentionally partial.

Add the import after line 2:

```ts
import { ForgeClient } from "../client";
import type { AgentConfig } from "../../types/agent";
```

And at line 43:

```ts
    const config = { apiVersion: "astromesh/v1", kind: "Agent" } as AgentConfig;
```

- [ ] **Step 5: Fix `@typescript-eslint/no-unused-vars`**

`StepModel.tsx:159` is `const { fallback: _, ...rest } = modelSpec;` — the codebase's idiom for omitting a key. The binding is unused by construction; that is the point. Express that in config rather than contorting the call site. In `eslint.config.js`, add a `rules` block immediately after the existing `languageOptions` block:

```js
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // `const { fallback: _, ...rest } = spec` is how this codebase omits a key.
      // The omitted binding is unused by construction — that is the point of the idiom.
      '@typescript-eslint/no-unused-vars': ['error', { ignoreRestSiblings: true }],
    },
```

`ignoreRestSiblings` only affects destructuring rest siblings; every other unused variable is still an error.

- [ ] **Step 6: Verify the build and tests still pass**

```bash
npm run build
npx vitest run
```

Expected: `✓ built in ~300ms` with no TypeScript errors, and `Test Files 5 passed (5)` / `Tests 20 passed (20)`.

- [ ] **Step 7: Verify exactly four problems are gone**

```bash
npx eslint . --format json 2>/dev/null | python3 -c "
import sys,json
from collections import Counter
d=json.load(sys.stdin)
rows=[(m['ruleId'],m['severity']) for f in d for m in f['messages']]
e=sum(1 for r in rows if r[1]==2)
print(f'{len(rows)} problems: {e} errors + {len(rows)-e} warnings')
for rule,n in Counter(r[0] for r in rows).most_common(): print(f'  {n:2}  {rule}')
"
```

Expected exactly:

```
16 problems: 14 errors + 2 warnings
  12  react-hooks/set-state-in-effect
   2  react-hooks/exhaustive-deps
   1  react-hooks/preserve-manual-memoization
   1  react-hooks/static-components
```

Every remaining problem must be a `react-hooks/*` rule. If any `prefer-const`, `no-unused-vars`, `no-explicit-any` or `only-export-components` survives, the fix above missed a site.

- [ ] **Step 8: Confirm the lockfile did not drift**

```bash
cd .. && git status --short astromesh-forge/package-lock.json
```

Expected: empty output. If the lockfile is modified, `npm install` was used somewhere instead of `npm ci` — revert it with `git checkout astromesh-forge/package-lock.json`.

- [ ] **Step 9: Commit**

```bash
git add astromesh-forge/src/utils/pipeline-graph.ts \
        astromesh-forge/src/components/console/ConsoleRightPanel.tsx \
        astromesh-forge/src/api/__tests__/client.test.ts \
        astromesh-forge/eslint.config.js
git commit -m "fix(forge): resolver los 4 errores de lint que TypeScript puede probar seguros

prefer-const en pipeline-graph (nextEdges se muta con push, nunca se reasigna),
el export innecesario de findSpanInTree (no lo importa nadie fuera de su archivo),
el as any del stub de config en client.test.ts (createAgent toma AgentConfig) y
ignoreRestSiblings para el idiom de omitir una clave por destructuring.

Ninguno cambia comportamiento en runtime: build verde y los 20 tests siguen
pasando. Lint queda en 16 problemas, todos react-hooks/*.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Document the 16 deferred hook violations

Each of these changes what React does at runtime, in a component with no test coverage. They get a per-site `eslint-disable-next-line` with a written reason — greppable debt, not a blanket rule-off. The rules stay enabled, so a *new* violation anywhere else still fails the gate.

**Files:**
- Modify: `astromesh-forge/src/components/canvas/panels/PipelinePropertiesPanel.tsx` (lines 107, 157, 242, 316, 411)
- Modify: `astromesh-forge/src/components/canvas/panels/Toolbox.tsx` (lines 102, 112)
- Modify: `astromesh-forge/src/components/console/ConsoleRightPanel.tsx` (lines 68, 71, 121, 130)
- Modify: `astromesh-forge/src/components/console/ConsoleShell.tsx` (line 44)
- Modify: `astromesh-forge/src/components/console/SpanNode.tsx` (line 104)
- Modify: `astromesh-forge/src/components/templates/TemplateGallery.tsx` (line 33)
- Modify: `astromesh-forge/src/components/templates/TemplatePreview.tsx` (line 44)
- Modify: `astromesh-forge/src/components/wizard/StepTools.tsx` (line 145)

**Interfaces:**
- Consumes: Task 1's tree (16 problems, all `react-hooks/*`).
- Produces: `npx eslint . --max-warnings 0` exits 0. Task 3 gates on that.

**Line numbers shift as you insert comments.** Do not work down a stale list: re-run the reporter (Step 1) after each file, and always fix the *lowest* file first or insert bottom-up within a file.

- [ ] **Step 1: Get the current violation list**

```bash
cd astromesh-forge
npx eslint . --format json 2>/dev/null | python3 -c "
import sys,json; d=json.load(sys.stdin)
for f in d:
    p=f['filePath'].split('astromesh-forge/')[-1]
    for m in f['messages']: print(f\"{p}:{m['line']}  {m['ruleId']}\")
"
```

- [ ] **Step 2: Disable the props-to-state sync sites**

For each `react-hooks/set-state-in-effect` in `PipelinePropertiesPanel.tsx` (5 sites), `TemplatePreview.tsx:44`, `TemplateGallery.tsx:33`, `StepTools.tsx:145`, `ConsoleShell.tsx:44` and `ConsoleRightPanel.tsx:68` — these sync incoming props into local form state inside an effect. Insert directly above the flagged line:

```ts
      // eslint-disable-next-line react-hooks/set-state-in-effect -- syncs props into local
      // form state; the idiomatic fix is remounting via `key` or deriving during render.
      // Deferred: this component has no test coverage. See the hook-refactor spec.
```

Match the surrounding indentation exactly.

- [ ] **Step 3: Disable the fetch-in-effect sites**

`Toolbox.tsx:102` and `:112` fetch and set state (`.then(setAgents)`, `.then(setBuiltinTools)`). Insert directly above each flagged line:

```ts
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-then-setState;
    // the idiomatic fix is moving fetching out of the effect into the data layer.
    // Deferred: this component has no test coverage. See the hook-refactor spec.
```

- [ ] **Step 4: Disable the three remaining hook rules**

`ConsoleRightPanel.tsx` `exhaustive-deps` (2 sites) — adding the missing dependency can turn a stable effect into a render loop, and nothing here would catch it:

```ts
    // eslint-disable-next-line react-hooks/exhaustive-deps -- adding the dep risks a render
    // loop; deferred with the rest of the hook debt. This component has no test coverage.
```

`ConsoleRightPanel.tsx` `preserve-manual-memoization`:

```ts
    // eslint-disable-next-line react-hooks/preserve-manual-memoization -- deferred with the
    // rest of the hook debt. This component has no test coverage.
```

`SpanNode.tsx:104` `static-components`:

```ts
  // eslint-disable-next-line react-hooks/static-components -- component defined inline;
  // hoisting it changes remount behaviour. Deferred: no test coverage for this component.
```

- [ ] **Step 5: Verify the lint is green with zero warnings**

```bash
npx eslint . --max-warnings 0; echo "exit=$?"
```

Expected: no output and `exit=0`.

- [ ] **Step 6: Verify every disable carries a reason**

```bash
grep -rn "eslint-disable" src/ | grep -v -- "--" && echo "FALLA: hay un disable sin razon" || echo "OK: todos los disables estan justificados"
```

Expected: `OK: todos los disables estan justificados`.

- [ ] **Step 7: Verify the debt is greppable and complete**

```bash
grep -rc "eslint-disable-next-line react-hooks" src/ | grep -v ":0" | awk -F: '{s+=$2} END {print s" sitios documentados (esperado: 16)"}'
```

Expected: `16 sitios documentados (esperado: 16)`.

- [ ] **Step 8: Verify nothing else changed**

```bash
npm run build && npx vitest run
```

Expected: build green, `Tests 20 passed (20)`. Comments cannot change behaviour — this confirms no code was touched by accident.

- [ ] **Step 9: Commit**

```bash
cd .. && git add astromesh-forge/src
git commit -m "chore(forge): documentar los 16 sitios de deuda de hooks con su justificacion

Cada eslint-disable lleva escrito el patron y el arreglo idiomatico que se
posterga. Son sitios que cambian comportamiento de React en componentes sin
cobertura de tests (el unico test de componente es App.test.tsx), asi que
refactorizarlos sin red es exactamente lo que el gate viene a evitar.

Las reglas quedan activas: una violacion nueva en cualquier otro lado falla.
La deuda es grepeable con 'eslint-disable-next-line react-hooks'.

Lint queda verde con --max-warnings 0; build y los 20 tests sin cambios.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: The `test` script and the `test-forge` CI gate

The deliverable. Forge has vitest, jsdom and 5 passing test files with no npm entry point; the gate needs one. Then the job, which must be **proven to bite** — a gate observed only passing is not a verified gate.

**Files:**
- Modify: `astromesh-forge/package.json` (`scripts`, `engines`)
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: Task 2's tree (`eslint . --max-warnings 0` exits 0).
- Produces: `npm test` → `vitest run`; a `test-forge` job gating lint + test + build.

- [ ] **Step 1: Resolve the Node version by running it**

Three independent reasons Node 22 is the right pin: `vite@8.0.1` declares `node: ^20.19.0 || >=22.12.0`; `vitest@4.1.0` declares `node: ^20.0.0 || ^22.0.0 || >=24.0.0`; and `.github/workflows/docs.yml` already builds `docs-site` (Astro, i.e. Vite) on `node-version: 22` in this repo's CI today. Node 20 reached EOL in April 2026.

Engine ranges are a declaration of intent, not proof — verify by running it:

```bash
cd astromesh-forge
node --version   # if not 22.x, install it (e.g. `nvm install 22 && nvm use 22`)
npm ci && npx eslint . --max-warnings 0 && npx vitest run && npm run build
```

Expected: all green on Node 22. If anything fails on 22 but passes on 20.20.2, pin the job to `20` in Step 3, set `engines` to `>=20.19` in Step 2, and report the Node 22 failure as an explicit follow-up — do not silently defer it.

- [ ] **Step 2: Add the `test` script and `engines`**

In `astromesh-forge/package.json`, extend `scripts` and add `engines` after it:

```json
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "eslint .",
    "test": "vitest run",
    "preview": "vite preview"
  },
  "engines": {
    "node": ">=22.12"
  },
```

- [ ] **Step 3: Verify `npm test` works**

```bash
npm test
```

Expected: `Test Files 5 passed (5)` / `Tests 20 passed (20)`.

- [ ] **Step 4: Add the `test-forge` job**

In `.github/workflows/ci.yml`, append after the existing `test-orbit` job, matching its shape:

```yaml
  test-forge:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      # setup-node@v6, matching ci.yml's convention of recent majors (checkout@v7,
      # setup-python@v6). v7.0.0 exists but shipped 2026-07-14 — too fresh to adopt
      # blind. docs.yml still pins @v4; this is the newer of the two in-repo shapes.
      - uses: actions/setup-node@v6
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: astromesh-forge/package-lock.json
      # `ci`, not `install`: the lockfile is authoritative and must not drift.
      - name: Install dependencies
        working-directory: astromesh-forge
        run: npm ci
      - name: Lint
        working-directory: astromesh-forge
        # --max-warnings 0: eslint exits 0 on warnings by default, which is how this
        # suite drifted red unnoticed in the first place.
        run: npx eslint . --max-warnings 0
      - name: Tests
        working-directory: astromesh-forge
        run: npm test
      - name: Build
        working-directory: astromesh-forge
        run: npm run build
```

- [ ] **Step 5: Validate the workflow YAML**

```bash
cd .. && python3 -c "
import yaml; w=yaml.safe_load(open('.github/workflows/ci.yml'))
print('OK: YAML valido')
for j in w['jobs']: print(f'  {j}')
"
```

Expected: valid YAML listing `test`, `test-node`, `test-cli`, `test-orbit` and `test-forge`.

No path filter: `test-forge` runs on every push, exactly like its four siblings. GitHub Actions has no native per-job path filter, and the alternatives — a third-party action like `dorny/paths-filter`, or splitting Forge into its own workflow file — both cost more than they save. Adding a third-party action to the build chain to save roughly a minute of CI is a bad trade, and a second workflow would break the single-`CI`-badge convention the README links to. If Forge's job ever becomes slow enough to matter, moving it to its own workflow with a native `on.push.paths` filter is the cheap fix.

- [ ] **Step 7: Commit and push**

```bash
git add astromesh-forge/package.json .github/workflows/ci.yml
git commit -m "ci(forge): gatear build, tests y lint de Forge en CI

Forge no estaba en ningun workflow: por eso su lint quedo rojo desde marzo (18
errores) sin que nadie se enterara, mientras el build y los 20 tests seguian
verdes. Es el mismo patron que la suite de Orbit antes de test-orbit.

Agrega el script `test` (habia vitest, jsdom y 5 archivos de test sin forma de
correrlos por npm) y el job test-forge, hermano de test-orbit. Corre solo cuando
cambia astromesh-forge/ o el propio ci.yml: es un SPA que no depende de los
paquetes Python.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git push origin develop
```

- [ ] **Step 8: Verify the job runs green on the real CI**

```bash
gh run list --workflow=ci.yml --limit 1
gh run watch <run-id> --exit-status; echo "exit=$?"
```

Expected: `exit=0`, with `test-forge` present and green.

- [ ] **Step 9: PROVE THE GATE BITES — this step is not optional**

A gate observed only passing is not a verified gate. This repo has already shipped a workflow whose build jobs were green while the artifact it published did not boot. Break each gated dimension on a scratch branch and confirm CI goes red for each.

Create the scratch branch and a file that violates all three dimensions at once — one push, one CI run, three verdicts:

```bash
git checkout -b scratch/prove-forge-gate
cat > astromesh-forge/src/utils/gate-probe.ts <<'PROBE'
// Temporary: proves the CI gate rejects each dimension. Deleted in this same task.
export const typeError: number = "this is not a number"; // (b) build must fail
export function lintViolation() {
  let never = 1; // (c) prefer-const — lint must fail
  return never;
}
PROBE
cat > astromesh-forge/src/utils/__tests__/gate-probe.test.ts <<'PROBE'
import { describe, it, expect } from "vitest";
// Temporary: proves the CI gate rejects a failing test. Deleted in this same task.
describe("gate probe", () => {
  it("fails on purpose", () => {
    expect(1).toBe(2); // (a) test must fail
  });
});
PROBE
git add astromesh-forge/src/utils/gate-probe.ts astromesh-forge/src/utils/__tests__/gate-probe.test.ts
git commit -m "test: probar que el gate de forge detecta test roto, error de tipos y lint"
git push origin scratch/prove-forge-gate
```

Open a PR against `develop` and read the `test-forge` job. Confirm all three, individually:

- **(a) failing test** → the `Tests` step fails on `gate-probe.test.ts`.
- **(b) type error** → the `Build` step fails with a TypeScript error on `gate-probe.ts`.
- **(c) lint violation** → the `Lint` step fails with `prefer-const` on `gate-probe.ts`.

Lint runs before tests and build, so the job stops at the first failure. To see each dimension fail on its own, either read the failing step and delete that probe to expose the next, or run the three steps locally where nothing short-circuits them:

```bash
cd astromesh-forge
npx eslint . --max-warnings 0; echo "lint exit=$?    (esperado: 1)"
npm test;                     echo "test exit=$?    (esperado: 1)"
npm run build;                echo "build exit=$?   (esperado: 2)"
```

Then remove the probe entirely and confirm the branch is clean:

```bash
cd .. && git checkout develop
git push origin --delete scratch/prove-forge-gate
git branch -D scratch/prove-forge-gate
git status --short   # esperado: vacio — ningun archivo de prueba sobreviviente
```

Report the three outcomes explicitly. If any dimension does NOT go red, the gate is broken — fix it before proceeding. Do not report this task complete on the strength of a green run alone.

---

### Task 4: Version bump

**Files:**
- Modify: `astromesh-forge/package.json` (`version`)

**Interfaces:**
- Consumes: Tasks 1–3 complete and green.
- Produces: nothing downstream.

**Note:** the changelog entry is NOT here. `CLAUDE.md` makes it mandatory that a `fix:`/`feat:`/`refactor:` commit carry its changelog entry in the same commit or the one immediately before, so the umbrella entry is front-loaded into Task 1 instead — the repo's convention for a feature series. This task only bumps the version.

- [ ] **Step 1: Bump the version to 0.24.0**

In `astromesh-forge/package.json`:

```json
  "version": "0.24.0",
```

Forge follows its own line (adk is at 0.2.0, orbit at 0.4.0, node/cli at 0.1.1 — no sub-package tracks the core's 0.34.0). Forge changed in this plan, so it earns a bump. Do NOT touch `pyproject.toml`, `astromesh/__init__.py`, or any other package's version.

- [ ] **Step 2: Verify nothing else moved**

```bash
git diff --stat
```

Expected: exactly `astromesh-forge/package.json`. If `pyproject.toml` or another package's version appears, revert it. The changelog entry already landed in Task 1 — do not add a second one.

- [ ] **Step 3: Commit and push**

```bash
git add astromesh-forge/package.json
git commit -m "chore(forge): v0.24.0 — gate de CI y lint verde

Forge bumpea en su propia linea, como el resto de los sub-paquetes; no sigue al
core (0.34.0). Es private y nunca se publica a npm, asi que el numero es una
etiqueta interna.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git push origin develop
```

- [ ] **Step 5: Verify CI is green on develop**

```bash
gh run list --workflow=ci.yml --limit 1
gh run watch <run-id> --exit-status; echo "exit=$?"
```

Expected: `exit=0`.

---

## Done when

- `npm run lint`, `npm test` and `npm run build` are green in `astromesh-forge/`, locally and in CI.
- `test-forge` runs on Forge changes and is **demonstrated red** for a broken test, a type error, and a fresh lint violation (Task 3 Step 9).
- Forge is at 0.24.0 with its changelog entry.
- `grep -rn "eslint-disable-next-line react-hooks" astromesh-forge/src/` lists 16 sites, each with a written reason.
- No React runtime behaviour changed: the same 20 tests pass, unchanged, throughout.
