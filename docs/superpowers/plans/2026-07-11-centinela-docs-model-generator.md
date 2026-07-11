# Centinela Docs — Model Card Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate rich Astro Starlight model-card pages for the Astromesh docs site from the foundry's `catalog.lock.json`, so model docs always reflect the machine contract instead of drifting hand-authored pages.

**Architecture:** A vendored copy of the nebula lock lives in `docs-site/src/data/catalog.lock.json` (committed), refreshed by a dependency-free `sync-catalog.mjs`. A `gen-models.mjs` generator (pure `renderModels(lock)` core + thin I/O wrapper) writes gitignored MDX into `src/content/docs/models/`, wired to run in npm `prebuild`/`predev`. A static "Models" sidebar group uses Starlight `autogenerate`.

**Tech Stack:** Node ≥22 (built-ins only: `fs`, `path`, `url`, `node:test`), Astro 5 + Starlight 0.34. Zero new npm dependencies.

## Global Constraints

- **Repo:** all work in `astromesh`, on a branch `feat/centinela-docs-generator` off `develop`.
- **Zero new dependencies.** Generator and tests use Node built-ins only (`node:fs`, `node:path`, `node:url`, `node:test`, `node:assert`).
- **Node ≥22** (matches `docs.yml`). ES modules (`.mjs`, `import`/`export`).
- **Supported `schema_version`:** `"1"` only. Unsupported → throw loudly.
- **Released status regex:** `/^[0-9a-f]{7,40}$/` applied to the primary revision `sha`.
- **Generated MDX is gitignored** — never commit `src/content/docs/models/`.
- **`docs.yml` is NOT modified** — it already runs `npm run build` which triggers `prebuild`.
- **Do not touch** the nebula repo, the runtime, or the provider.
- **Conventional commits**, each ending with a trailer line:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Work from `docs-site/` for npm/node commands unless a path says otherwise.

## File Structure

New:
- `docs-site/src/data/catalog.lock.json` — vendored lock (committed source of truth on docs side).
- `docs-site/scripts/sync-catalog.mjs` — refresh the vendored lock from a sibling nebula checkout; exports `validateLock`, `sync`.
- `docs-site/scripts/sync-catalog.test.mjs` — unit tests for `validateLock`.
- `docs-site/scripts/gen-models.mjs` — exports pure `renderModels(lock)`, `resolvePrimaryRevision`, `deriveStatus`, and I/O `generate({lockPath,outDir})`.
- `docs-site/scripts/gen-models.test.mjs` — unit tests for the render core.

Modified:
- `docs-site/package.json` — add `gen:models`, `prebuild`, `predev`, `sync:catalog`, `test`.
- `docs-site/.gitignore` — ignore generated `models/` dir (create the file if absent).
- `docs-site/astro.config.mjs` — add the "Models" sidebar group after "Reference".

Generated (gitignored):
- `docs-site/src/content/docs/models/index.mdx`
- `docs-site/src/content/docs/models/<name>.mdx`

---

### Task 1: Vendored lock + `sync-catalog.mjs`

**Files:**
- Create: `docs-site/src/data/catalog.lock.json`
- Create: `docs-site/scripts/sync-catalog.mjs`
- Test: `docs-site/scripts/sync-catalog.test.mjs`
- Modify: `docs-site/package.json`

**Interfaces:**
- Produces: `validateLock(obj) -> void` (throws on invalid); `sync({source?, dest?}) -> {source, dest, models}`.

- [ ] **Step 0: Create the branch**

Run (from `/Users/fulfaro/monaccode/astromesh`):
```bash
git checkout develop && git checkout -b feat/centinela-docs-generator
```

- [ ] **Step 1: Write the vendored lock file**

Create `docs-site/src/data/catalog.lock.json` with exactly this content (a verbatim copy of the current nebula lock):

```json
{
  "models": [
    {
      "aliases": {
        "prod": "v0.1"
      },
      "contract": {
        "labels": [
          "positivo",
          "neutral",
          "negativo"
        ],
        "validation": "constrain_label"
      },
      "hf_repo": "astromesh/Centinela-Qwen3-4B",
      "kind": "classifier",
      "name": "centinela-sentiment",
      "revisions": {
        "v0.1": {
          "base_model": "Qwen/Qwen3-4B",
          "dataset": "centinela-sentiment-es@1",
          "eval": {
            "invalid_rate": 0.0,
            "macro_f1": 0.0
          },
          "formats": [
            "safetensors",
            "gguf"
          ],
          "gate": "passed",
          "scout_rationale": "",
          "sha": "REPLACE_WITH_REAL_HF_REVISION_SHA",
          "train_config_hash": "sha256:REPLACE_WITH_REAL_TRAIN_CONFIG_HASH",
          "version": "v0.1"
        }
      },
      "task": "text-classification",
      "vertical": "finanzas"
    }
  ],
  "schema_version": "1"
}
```

- [ ] **Step 2: Write the failing test**

Create `docs-site/scripts/sync-catalog.test.mjs`:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateLock } from './sync-catalog.mjs';

test('validateLock accepts a well-formed lock', () => {
  assert.doesNotThrow(() => validateLock({ schema_version: '1', models: [] }));
});

test('validateLock rejects a non-object', () => {
  assert.throws(() => validateLock(null), /expected a JSON object/);
  assert.throws(() => validateLock([]), /expected a JSON object/);
});

test('validateLock rejects an unsupported schema_version', () => {
  assert.throws(
    () => validateLock({ schema_version: '2', models: [] }),
    /unsupported schema_version/,
  );
});

test('validateLock rejects a missing models array', () => {
  assert.throws(() => validateLock({ schema_version: '1' }), /"models" must be an array/);
});
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `docs-site/`): `node --test scripts/sync-catalog.test.mjs`
Expected: FAIL — cannot resolve `./sync-catalog.mjs` (module not found).

- [ ] **Step 4: Write `sync-catalog.mjs`**

Create `docs-site/scripts/sync-catalog.mjs`:

```js
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SUPPORTED_SCHEMA_VERSIONS = new Set(['1']);

/** Throws if `obj` is not a lock we can vendor. Dependency-free (no JSON Schema lib). */
export function validateLock(obj) {
  if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) {
    throw new Error('Invalid lock: expected a JSON object');
  }
  if (!SUPPORTED_SCHEMA_VERSIONS.has(String(obj.schema_version))) {
    throw new Error(
      `Invalid lock: unsupported schema_version ${obj.schema_version} ` +
        `(supported: ${[...SUPPORTED_SCHEMA_VERSIONS].join(', ')})`,
    );
  }
  if (!Array.isArray(obj.models)) {
    throw new Error('Invalid lock: "models" must be an array');
  }
}

const HERE = dirname(fileURLToPath(import.meta.url));
const DOCS_SITE = join(HERE, '..'); // docs-site/
const ASTROMESH_ROOT = join(DOCS_SITE, '..'); // astromesh/
const DEFAULT_SOURCE = resolve(
  ASTROMESH_ROOT,
  '..',
  'astromesh-nebula',
  'nebula',
  'catalog.lock.json',
);
const DEST = join(DOCS_SITE, 'src', 'data', 'catalog.lock.json');

/** Copy + validate the nebula lock into the vendored docs location. */
export function sync({ source = DEFAULT_SOURCE, dest = DEST } = {}) {
  if (!existsSync(source)) {
    throw new Error(
      `Catalog lock not found at ${source}. Check out astromesh-nebula next to astromesh, ` +
        `or pass an explicit path: node scripts/sync-catalog.mjs <path-to-catalog.lock.json>`,
    );
  }
  const raw = readFileSync(source, 'utf8');
  let obj;
  try {
    obj = JSON.parse(raw);
  } catch (err) {
    throw new Error(`Catalog lock at ${source} is not valid JSON: ${err.message}`);
  }
  validateLock(obj);
  writeFileSync(dest, `${JSON.stringify(obj, null, 2)}\n`);
  return { source, dest, models: obj.models.length };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  const override = process.argv[2];
  const { source, dest, models } = sync(override ? { source: resolve(override) } : {});
  console.log(`sync-catalog: copied ${models} model(s) from ${source} -> ${dest}`);
}
```

- [ ] **Step 5: Run test to verify it passes**

Run (from `docs-site/`): `node --test scripts/sync-catalog.test.mjs`
Expected: PASS — 4 tests, output pristine.

- [ ] **Step 6: Add package.json scripts**

Modify `docs-site/package.json` — add to `"scripts"`:
```json
    "sync:catalog": "node scripts/sync-catalog.mjs",
    "test": "node --test scripts/"
```

- [ ] **Step 7: Verify the round-trip (idempotence check)**

Run (from `docs-site/`): `npm run sync:catalog`
Expected: prints `sync-catalog: copied 1 model(s) ...`; `git diff --stat src/data/catalog.lock.json` shows **no change** (the vendored file already matches nebula). If nebula is not checked out beside astromesh, this step is expected to error with the "not found" message — that is acceptable; the committed vendored file from Step 1 stands.

- [ ] **Step 8: Commit**

```bash
git add docs-site/src/data/catalog.lock.json docs-site/scripts/sync-catalog.mjs \
        docs-site/scripts/sync-catalog.test.mjs docs-site/package.json
git commit -m "feat(docs): vendored catalog lock + sync-catalog script

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `gen-models.mjs` render core

**Files:**
- Create: `docs-site/scripts/gen-models.mjs` (render core only; I/O wrapper added in Task 3)
- Test: `docs-site/scripts/gen-models.test.mjs`

**Interfaces:**
- Consumes: the vendored lock shape (`{schema_version, models:[{name,kind,task,vertical,hf_repo,contract:{labels,validation},aliases:{<alias>:<rev>},revisions:{<rev>:{base_model,dataset,gate,train_config_hash,formats,sha,version,eval:{macro_f1,invalid_rate}}}}]}`).
- Produces: `renderModels(lock) -> { cards: [{slug, mdx}], index: {mdx} }`; `resolvePrimaryRevision(model) -> {key, rev} | null`; `deriveStatus(model) -> 'released' | 'preview'`.

- [ ] **Step 1: Write the failing tests**

Create `docs-site/scripts/gen-models.test.mjs`:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderModels, deriveStatus, resolvePrimaryRevision } from './gen-models.mjs';

function model(overrides = {}) {
  return {
    name: 'centinela-sentiment',
    kind: 'classifier',
    task: 'text-classification',
    vertical: 'finanzas',
    hf_repo: 'astromesh/Centinela-Qwen3-4B',
    contract: { labels: ['positivo', 'neutral', 'negativo'], validation: 'constrain_label' },
    aliases: { prod: 'v0.1' },
    revisions: {
      'v0.1': {
        base_model: 'Qwen/Qwen3-4B',
        dataset: 'centinela-sentiment-es@1',
        gate: 'passed',
        train_config_hash: 'sha256:deadbeef',
        formats: ['safetensors', 'gguf'],
        sha: 'a'.repeat(40),
        version: 'v0.1',
        eval: { macro_f1: 0.91, invalid_rate: 0.0 },
      },
    },
    ...overrides,
  };
}

function lock(models) {
  return { schema_version: '1', models };
}

test('rich card renders every section', () => {
  const { cards } = renderModels(lock([model()]));
  assert.equal(cards.length, 1);
  const { slug, mdx } = cards[0];
  assert.equal(slug, 'centinela-sentiment');
  assert.match(mdx, /title: centinela-sentiment/);
  assert.match(mdx, /import \{ Aside, Badge \} from '@astrojs\/starlight\/components';/);
  assert.match(mdx, /`positivo` · `neutral` · `negativo`/);
  assert.match(mdx, /\[astromesh\/Centinela-Qwen3-4B\]\(https:\/\/huggingface\.co\/astromesh\/Centinela-Qwen3-4B\)/);
  assert.match(mdx, /## Aliases/);
  assert.match(mdx, /\| prod \| v0\.1 \|/);
  assert.match(mdx, /## Revisions/);
  assert.match(mdx, /Qwen\/Qwen3-4B/);
  assert.match(mdx, /centinela-sentiment-es@1/);
  assert.match(mdx, /## Revision detail/);
  assert.match(mdx, /sha256:deadbeef/);
  assert.match(mdx, /`safetensors`, `gguf`/);
  assert.match(mdx, /## Serving/);
  assert.match(mdx, /SentimentResult\.score = None/);
  assert.match(mdx, /## How to use/);
  assert.match(mdx, /apiVersion: astromesh\/v1/);
  assert.match(mdx, /model: centinela-sentiment/);
});

test('released status when gate passed and sha is a real hash', () => {
  assert.equal(deriveStatus(model()), 'released');
  const { cards } = renderModels(lock([model()]));
  assert.match(cards[0].mdx, /<Badge text="released" variant="success" \/>/);
});

test('preview status when sha is a placeholder', () => {
  const m = model();
  m.revisions['v0.1'].sha = 'REPLACE_WITH_REAL_HF_REVISION_SHA';
  assert.equal(deriveStatus(m), 'preview');
  const { cards } = renderModels(lock([m]));
  assert.match(cards[0].mdx, /<Badge text="preview" variant="caution" \/>/);
  assert.match(cards[0].mdx, /<Aside type="caution" title="Preliminary">/);
});

test('multiple revisions without a prod alias => preview (no latest guessing)', () => {
  const m = model({ aliases: {} });
  m.revisions['v0.2'] = { ...m.revisions['v0.1'], version: 'v0.2' };
  assert.equal(resolvePrimaryRevision(m), null);
  assert.equal(deriveStatus(m), 'preview');
});

test('index groups by vertical and links each model', () => {
  const { index } = renderModels(lock([model()]));
  assert.match(index.mdx, /## finanzas/);
  assert.match(index.mdx, /\[centinela-sentiment\]\(\/astromesh\/models\/centinela-sentiment\/\)/);
  assert.match(index.mdx, /\| centinela-sentiment \| text-classification \| classifier \| released \|/);
});

test('empty catalog renders a friendly index and no cards', () => {
  const { cards, index } = renderModels(lock([]));
  assert.equal(cards.length, 0);
  assert.match(index.mdx, /No published models yet/);
});

test('unsupported schema_version throws', () => {
  assert.throws(() => renderModels({ schema_version: '2', models: [] }), /Unsupported catalog schema_version/);
});

test('alias pointing at an unknown revision throws', () => {
  const m = model({ aliases: { prod: 'v9.9' } });
  assert.throws(() => renderModels(lock([m])), /unknown revision 'v9\.9'/);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `docs-site/`): `node --test scripts/gen-models.test.mjs`
Expected: FAIL — cannot resolve `./gen-models.mjs`.

- [ ] **Step 3: Write the render core**

Create `docs-site/scripts/gen-models.mjs`:

```js
const SUPPORTED_SCHEMA_VERSIONS = new Set(['1']);
const SHA_RE = /^[0-9a-f]{7,40}$/;

/** The revision a model's status/badges hang off, without guessing revision order. */
export function resolvePrimaryRevision(model) {
  const revisions = model.revisions ?? {};
  const prodTarget = model.aliases?.prod;
  if (prodTarget) {
    const rev = revisions[prodTarget];
    if (!rev) {
      throw new Error(
        `Malformed lock: model '${model.name}' alias 'prod' -> unknown revision '${prodTarget}'`,
      );
    }
    return { key: prodTarget, rev };
  }
  const keys = Object.keys(revisions);
  if (keys.length === 1) {
    return { key: keys[0], rev: revisions[keys[0]] };
  }
  return null; // multiple revisions, no prod alias => primary undefined by design
}

export function deriveStatus(model) {
  const primary = resolvePrimaryRevision(model);
  if (
    primary &&
    primary.rev.gate === 'passed' &&
    typeof primary.rev.sha === 'string' &&
    SHA_RE.test(primary.rev.sha)
  ) {
    return 'released';
  }
  return 'preview';
}

function assertAliasesResolve(model) {
  const revisions = model.revisions ?? {};
  for (const [alias, target] of Object.entries(model.aliases ?? {})) {
    if (!revisions[target]) {
      throw new Error(
        `Malformed lock: model '${model.name}' alias '${alias}' -> unknown revision '${target}'`,
      );
    }
  }
}

function fmtNum(n) {
  return typeof n === 'number' ? n.toFixed(2) : '—';
}

function renderCard(model) {
  assertAliasesResolve(model);
  const status = deriveStatus(model);
  const statusVariant = status === 'released' ? 'success' : 'caution';
  const labels = (model.contract?.labels ?? []).map((l) => `\`${l}\``).join(' · ') || '—';
  const revisions = model.revisions ?? {};
  const revKeys = Object.keys(revisions);

  const aliasEntries = Object.entries(model.aliases ?? {});
  const aliasTable = aliasEntries.length
    ? ['| Alias | Revision |', '|-------|----------|', ...aliasEntries.map(([a, r]) => `| ${a} | ${r} |`)].join('\n')
    : '_No aliases defined._';

  const revTable = [
    '| Version | Base model | Dataset | Gate | macro_f1 | invalid_rate |',
    '|---------|-----------|---------|------|----------|--------------|',
    ...revKeys.map((k) => {
      const rev = revisions[k];
      const e = rev.eval ?? {};
      return `| ${rev.version ?? k} | \`${rev.base_model ?? '—'}\` | \`${rev.dataset ?? '—'}\` | ${rev.gate ?? '—'} | ${fmtNum(e.macro_f1)} | ${fmtNum(e.invalid_rate)} |`;
    }),
  ].join('\n');

  const revDetail = revKeys
    .map((k) => {
      const rev = revisions[k];
      const formats = (rev.formats ?? []).map((f) => `\`${f}\``).join(', ') || '—';
      return [
        `### ${rev.version ?? k}`,
        '',
        `- **Base model:** \`${rev.base_model ?? '—'}\``,
        `- **Dataset:** \`${rev.dataset ?? '—'}\``,
        `- **Formats:** ${formats}`,
        `- **Train config hash:** \`${rev.train_config_hash ?? '—'}\``,
        `- **Revision SHA:** \`${rev.sha ?? '—'}\``,
      ].join('\n');
    })
    .join('\n\n');

  const primary = resolvePrimaryRevision(model);
  const gateBadge = primary ? `gate: ${primary.rev.gate ?? '—'}` : 'gate: n/a';

  const previewAside =
    status === 'preview'
      ? '\n<Aside type="caution" title="Preliminary">\nThis model is defined in the catalog but not yet published. The revision SHA and eval\nmetrics below are placeholders until the first release.\n</Aside>\n'
      : '';

  const aliasTarget = model.aliases?.prod ?? (revKeys.length === 1 ? revKeys[0] : 'prod');

  const mdx = `---
title: ${model.name}
description: ${model.kind} · ${model.vertical} · ${model.task}
---

import { Aside, Badge } from '@astrojs/starlight/components';

# ${model.name} <Badge text="${status}" variant="${statusVariant}" />

<Badge text="${model.vertical}" /> <Badge text="${model.task}" /> <Badge text="${model.kind}" /> <Badge text="${gateBadge}" />

**Hugging Face:** [${model.hf_repo}](https://huggingface.co/${model.hf_repo})
${previewAside}
## Contract

- **Labels:** ${labels}
- **Validation:** \`${model.contract?.validation ?? '—'}\`

## Aliases

${aliasTable}

## Revisions

${revTable}

## Revision detail

${revDetail}

## Serving

Served generatively via Text Generation Inference (TGI) on an OpenAI-compatible
\`/v1/chat/completions\` endpoint. Because generation yields no per-label probability,
the provider returns \`SentimentResult.score = None\`.

## How to use

Bind an alias to a live endpoint in \`config/centinela/bindings.yaml\`:

\`\`\`yaml
apiVersion: astromesh/v1
kind: CentinelaBindings
metadata:
  name: default
spec:
  bindings:
    - model: ${model.name}
      alias: ${aliasTarget}
      endpoint: https://your-endpoint.endpoints.huggingface.cloud
\`\`\`

Compile the bindings into a routable provider with \`astromeshctl centinela reconcile\`.
Agents then call the typed facade \`classify(text) -> SentimentResult\` (exposed as an ADK
tool), or route to the model through \`CentinelaProvider\` like any other provider.
`;

  return { slug: model.name, mdx };
}

function renderIndex(models) {
  if (!models.length) {
    return {
      mdx: `---
title: Models
description: Centinela model catalog
---

_No published models yet._
`,
    };
  }

  const byVertical = new Map();
  for (const m of models) {
    const v = m.vertical ?? 'other';
    if (!byVertical.has(v)) byVertical.set(v, []);
    byVertical.get(v).push(m);
  }

  const sections = [...byVertical.entries()]
    .map(([vertical, ms]) => {
      const rows = ms
        .map((m) => `| [${m.name}](/astromesh/models/${m.name}/) | ${m.task} | ${m.kind} | ${deriveStatus(m)} |`)
        .join('\n');
      return [`## ${vertical}`, '', '| Model | Task | Kind | Status |', '|-------|------|------|--------|', rows].join('\n');
    })
    .join('\n\n');

  return {
    mdx: `---
title: Models
description: Centinela model catalog
---

Models compiled from the foundry catalog. Each card is generated from
\`catalog.lock.json\` — the machine contract produced by the Nebula foundry.

${sections}
`,
  };
}

export function renderModels(lock) {
  if (!SUPPORTED_SCHEMA_VERSIONS.has(String(lock?.schema_version))) {
    throw new Error(
      `Unsupported catalog schema_version: ${lock?.schema_version} ` +
        `(supported: ${[...SUPPORTED_SCHEMA_VERSIONS].join(', ')})`,
    );
  }
  const models = Array.isArray(lock.models) ? lock.models : [];
  return { cards: models.map(renderCard), index: renderIndex(models) };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `docs-site/`): `node --test scripts/gen-models.test.mjs`
Expected: PASS — 8 tests, output pristine.

- [ ] **Step 5: Commit**

```bash
git add docs-site/scripts/gen-models.mjs docs-site/scripts/gen-models.test.mjs
git commit -m "feat(docs): gen-models render core (lock -> MDX cards + index)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: I/O wrapper + npm wiring + sidebar + integration build

**Files:**
- Modify: `docs-site/scripts/gen-models.mjs` (append `generate()` + direct-run block)
- Modify: `docs-site/scripts/gen-models.test.mjs` (add a `generate()` temp-dir test)
- Modify: `docs-site/package.json` (add `gen:models`, `prebuild`, `predev`)
- Modify: `docs-site/.gitignore` (create if absent)
- Modify: `docs-site/astro.config.mjs` (add "Models" sidebar group)

**Interfaces:**
- Consumes: `renderModels` from Task 2.
- Produces: `generate({lockPath?, outDir?}) -> {count}` — writes `index.mdx` + one `<slug>.mdx` per model into `outDir`, cleaning it first.

- [ ] **Step 1: Write the failing test**

Append to `docs-site/scripts/gen-models.test.mjs`:

```js
import { generate } from './gen-models.mjs';
import { mkdtempSync, writeFileSync, readFileSync, readdirSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

test('generate() writes index + one card per model and is idempotent', () => {
  const dir = mkdtempSync(join(tmpdir(), 'genmodels-'));
  const lockPath = join(dir, 'lock.json');
  const outDir = join(dir, 'models');
  writeFileSync(lockPath, JSON.stringify(lock([model()])));

  const first = generate({ lockPath, outDir });
  assert.equal(first.count, 1);
  assert.ok(existsSync(join(outDir, 'index.mdx')));
  assert.ok(existsSync(join(outDir, 'centinela-sentiment.mdx')));
  assert.match(readFileSync(join(outDir, 'centinela-sentiment.mdx'), 'utf8'), /title: centinela-sentiment/);

  // A stale file from a previous run must be cleaned.
  writeFileSync(join(outDir, 'stale.mdx'), 'stale');
  generate({ lockPath, outDir });
  assert.ok(!existsSync(join(outDir, 'stale.mdx')));
  assert.deepEqual(readdirSync(outDir).sort(), ['centinela-sentiment.mdx', 'index.mdx']);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `docs-site/`): `node --test scripts/gen-models.test.mjs`
Expected: FAIL — `generate` is not exported.

- [ ] **Step 3: Add the I/O wrapper**

Append to `docs-site/scripts/gen-models.mjs`:

```js
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const DOCS_SITE = join(HERE, '..');
const DEFAULT_LOCK = join(DOCS_SITE, 'src', 'data', 'catalog.lock.json');
const DEFAULT_OUT = join(DOCS_SITE, 'src', 'content', 'docs', 'models');

/** Read the vendored lock, render, and (re)write the models content directory. */
export function generate({ lockPath = DEFAULT_LOCK, outDir = DEFAULT_OUT } = {}) {
  const lock = JSON.parse(readFileSync(lockPath, 'utf8'));
  const { cards, index } = renderModels(lock);
  rmSync(outDir, { recursive: true, force: true });
  mkdirSync(outDir, { recursive: true });
  writeFileSync(join(outDir, 'index.mdx'), index.mdx);
  for (const card of cards) {
    writeFileSync(join(outDir, `${card.slug}.mdx`), card.mdx);
  }
  return { count: cards.length };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  const { count } = generate();
  console.log(`gen-models: wrote ${count} model card(s)`);
}
```

Note: ESM `import` statements hoist, so appending this block at the end of the file is
valid. `renderModels` (Task 2) is in the same module and in scope for `generate()`.

- [ ] **Step 4: Run tests to verify they pass**

Run (from `docs-site/`): `node --test scripts/gen-models.test.mjs`
Expected: PASS — 9 tests, output pristine.

- [ ] **Step 5: Wire npm scripts**

Modify `docs-site/package.json` `"scripts"` — add:
```json
    "gen:models": "node scripts/gen-models.mjs",
    "prebuild": "npm run gen:models",
    "predev": "npm run gen:models"
```

- [ ] **Step 6: Gitignore the generated directory**

Create or append to `docs-site/.gitignore`:
```
# Generated model cards (derived from src/data/catalog.lock.json)
src/content/docs/models/
```

- [ ] **Step 7: Add the "Models" sidebar group**

Modify `docs-site/astro.config.mjs` — insert this group in the `sidebar` array immediately **after** the `Reference` group object (and before `Agent Development Kit`):
```js
        {
          label: 'Models',
          autogenerate: { directory: 'models' },
        },
```

- [ ] **Step 8: Generate + integration build**

Run (from `docs-site/`):
```bash
npm run gen:models
npm run build
```
Expected: `gen-models: wrote 1 model card(s)`; then Astro builds with no errors and no
broken-link/component warnings referencing the models pages. Confirm
`dist/models/centinela-sentiment/index.html` exists:
```bash
ls dist/models/centinela-sentiment/index.html dist/models/index.html
```
Expected: both paths exist.

- [ ] **Step 9: Verify the generated dir is untracked**

Run (from repo root): `git status --porcelain docs-site/src/content/docs/models/`
Expected: **no output** (the directory is gitignored).

- [ ] **Step 10: Commit**

```bash
git add docs-site/scripts/gen-models.mjs docs-site/scripts/gen-models.test.mjs \
        docs-site/package.json docs-site/.gitignore docs-site/astro.config.mjs
git commit -m "feat(docs): generate model cards at build + Models sidebar

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Notes for the executor

- Run all `node`/`npm` commands from `docs-site/` unless the step says repo root.
- The generated `models/` directory only exists after `gen:models` runs; a clean
  checkout has none until `prebuild`/`predev` fires. This is intended.
- Do not add JSON Schema or any npm dependency — validation stays hand-rolled and
  dependency-free per the Global Constraints.
- If `npm run build` reports a broken link for the `astromeshctl`/provider references in
  the "How to use" section, those are prose (inline code), not links — no action needed.
