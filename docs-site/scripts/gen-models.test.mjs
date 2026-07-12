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
  // the binding must reference the alias NAME (prod), never the revision (v0.1)
  assert.match(mdx, /alias: prod/);
  assert.doesNotMatch(mdx, /alias: v0\.1/);
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
  assert.match(index.mdx, /\| text-classification \| classifier \| released \|/);
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
