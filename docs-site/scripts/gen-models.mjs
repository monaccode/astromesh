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

  // bindings.yaml `alias:` must hold an alias NAME (a key of model.aliases), not a
  // revision — the reconciler rejects anything that isn't a declared alias.
  const aliasNames = Object.keys(model.aliases ?? {});
  const aliasTarget = aliasNames.includes('prod') ? 'prod' : (aliasNames[0] ?? 'prod');

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
\`catalog.lock.json\` — the machine contract produced by the [Nebula foundry](/astromesh/nebula/introduction/).
To see how these models are trained, gated, and published, read
[The Foundry Pipeline](/astromesh/nebula/pipeline/).

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
