---
title: Knowledge Bundles (OKF)
description: Give an agent an Open Knowledge Format bundle and let it navigate the concepts it needs, with trust and freshness signals intact
---

import { Aside } from '@astrojs/starlight/components';

<Aside type="note">
The same reader is available outside Astromesh as the open-source library [astromesh-okf](/astromesh/okf/introduction/), for LangChain/LangGraph, CrewAI, Google ADK and more.
</Aside>

[Open Knowledge Format](https://github.com/GoogleCloudPlatform/open-knowledge-format) (OKF) is an open spec for knowledge as a directory of markdown files with YAML frontmatter, cross-linked like a wiki. Astromesh reads OKF v0.2 bundles (and v0.1 ones) as they are: no conversion, no embeddings, no vector store. The agent navigates the bundle with three tools and opens only what it needs.

## Configuration

```yaml
spec:
  knowledge:
    bundle: knowledge/acme_retail   # relative to the config directory, or absolute
```

`bundle` can sit next to `pipeline`; they are independent. If the directory does not exist the agent logs a warning and runs without it.

## What the agent gets

| Tool | Arguments | Returns |
|------|-----------|---------|
| `kb_index` | `path` (default `/`) | The directory's `index.md`, or one synthesized from the concepts' frontmatter when it is missing. |
| `kb_read` | `concept_id` | `type`, `title`, `trust`, `stale`, `warnings`, the body, unknown frontmatter under `extra`, and the body's `links` already resolved to concept ids. |
| `kb_find` | `text`, `type`, `tags`, `include_deprecated`, `limit` | Matching concepts (no body). Title, description and tag matches come before body matches. Deprecated concepts are left out unless asked for. |

The template variable `bundle_index` holds the root index. It is stable between queries while the bundle and its root concepts don't change (editing the bundle, or a root concept passing its `stale_after`, changes it), so it can go in `prompts.system` and keep the prompt cache warm, and it saves the agent its first `kb_index` call.

## Trust and freshness

Signals are reported, never used to hide a concept:

- `trust`: `human-reviewed` when any `verified` entry is by `human:…`, `machine-confirmed` when only agents or processes verified it, `unverified` otherwise.
- `stale`: true once `stale_after` has passed.
- `warnings`: plain sentences for the model, e.g. `DEPRECATED: kept for history; do not use for new work.`

Tell the agent what to do with them in its prompt. The example agent refuses deprecated sources and flags stale or draft ones.

## Tolerance

A concept is skipped only when its frontmatter cannot be parsed or has no `type`. Unknown types, unknown keys, missing optional fields and broken links are fine. `kb_index` and `kb_find` report how many concepts they skipped.

## Example

`config/agents/okf-demo.agent.yaml` answers support questions from `config/knowledge/okf-demo/`, a four-file bundle with a current policy, a deprecated one and a product reference.

## Security and limits

- The tools are read-only and never leave the bundle's root, symlinks included. Only `.md` concepts are read; nothing in the bundle is executed, including `Attested Computation` concepts.
- A concept's body reaches the model like any tool result. Mount bundles only from sources you trust.
- `kb_find` scans the whole bundle on each call. That is fine for hundreds to a few thousand concepts.
- Not supported yet: running Attested Computations, writing bundles, remote bundles (git or tarball), ingesting a bundle into a `RAGPipeline`.
