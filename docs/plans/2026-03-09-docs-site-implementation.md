# Astromesh Documentation Site — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an interactive documentation site with Starlight (Astro) covering all Astromesh features, deployment modes, and configuration — deployed to GitHub Pages via CI.

**Architecture:** Starlight project in `docs-site/` at repo root. Content pages in `docs-site/src/content/docs/` organized by user journey (Getting Started → Architecture → Configuration → Deployment → Advanced → Reference). Four interactive Astro island components for the landing page. GitHub Actions workflow deploys on push to `develop`.

**Tech Stack:** Astro + Starlight, MDX for landing page, CSS animations for pipeline diagram, GitHub Actions + `actions/deploy-pages`.

**Source docs:** All existing `.md` files in `docs/` serve as content base. Each page expands significantly beyond the originals with step-by-step instructions, examples, and troubleshooting.

---

## Task 1: Scaffold Starlight Project

**Files:**
- Create: `docs-site/package.json`
- Create: `docs-site/astro.config.mjs`
- Create: `docs-site/tsconfig.json`
- Create: `docs-site/src/content/config.ts`

**Step 1: Initialize Starlight project**

```bash
cd docs-site
npm create astro@latest -- --template starlight --yes
```

If interactive prompts block, create files manually instead.

**Step 2: Create `package.json`**

```json
{
  "name": "astromesh-docs",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "astro dev",
    "build": "astro build",
    "preview": "astro preview"
  },
  "dependencies": {
    "@astrojs/starlight": "^0.34",
    "astro": "^5.7",
    "sharp": "^0.33"
  }
}
```

Run: `cd docs-site && npm install`

**Step 3: Create `astro.config.mjs`**

```js
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://monaccode.github.io',
  base: '/astromech-platform',
  integrations: [
    starlight({
      title: 'Astromesh',
      description: 'AI Agent Runtime Platform',
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/monaccode/astromech-platform' },
      ],
      sidebar: [
        {
          label: 'Getting Started',
          items: [
            { label: 'What is Astromesh?', slug: 'getting-started/what-is-astromesh' },
            { label: 'Installation', slug: 'getting-started/installation' },
            { label: 'Quick Start', slug: 'getting-started/quickstart' },
            { label: 'Your First Agent', slug: 'getting-started/first-agent' },
          ],
        },
        {
          label: 'Architecture',
          items: [
            { label: 'Overview', slug: 'architecture/overview' },
            { label: 'Four-Layer Design', slug: 'architecture/four-layer-design' },
            { label: 'Agent Execution Pipeline', slug: 'architecture/agent-pipeline' },
            { label: 'Kubernetes-Style Architecture', slug: 'architecture/k8s-architecture' },
          ],
        },
        {
          label: 'Configuration',
          items: [
            { label: 'Init Wizard', slug: 'configuration/init-wizard' },
            { label: 'Agent YAML Schema', slug: 'configuration/agent-yaml' },
            { label: 'Provider Configuration', slug: 'configuration/providers' },
            { label: 'Runtime Config', slug: 'configuration/runtime-config' },
            { label: 'Profiles Reference', slug: 'configuration/profiles' },
            { label: 'Channels', slug: 'configuration/channels' },
          ],
        },
        {
          label: 'Deployment',
          items: [
            { label: 'Standalone (from source)', slug: 'deployment/standalone' },
            { label: 'Astromesh OS', slug: 'deployment/astromesh-os' },
            { label: 'Docker Single Node', slug: 'deployment/docker-single' },
            { label: 'Docker Maia', slug: 'deployment/docker-maia' },
            { label: 'Docker Maia + GPU', slug: 'deployment/docker-maia-gpu' },
            { label: 'Helm / Kubernetes', slug: 'deployment/helm-kubernetes' },
            { label: 'ArgoCD / GitOps', slug: 'deployment/argocd-gitops' },
          ],
        },
        {
          label: 'Advanced',
          items: [
            { label: 'Rust Native Extensions', slug: 'advanced/rust-extensions' },
            { label: 'WhatsApp Integration', slug: 'advanced/whatsapp' },
            { label: 'Observability Stack', slug: 'advanced/observability' },
            { label: 'Maia Protocol Internals', slug: 'advanced/maia-internals' },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'Runtime Engine', slug: 'reference/core/runtime-engine' },
            { label: 'Model Router', slug: 'reference/core/model-router' },
            { label: 'Tool Registry', slug: 'reference/core/tool-registry' },
            { label: 'Memory Manager', slug: 'reference/core/memory-manager' },
            { label: 'Daemon (astromeshd)', slug: 'reference/os/daemon' },
            { label: 'CLI (astromeshctl)', slug: 'reference/os/cli' },
            { label: 'Gossip Protocol', slug: 'reference/mesh/gossip-protocol' },
            { label: 'Scheduling & Routing', slug: 'reference/mesh/scheduling' },
            { label: 'Environment Variables', slug: 'reference/env-vars' },
            { label: 'API Endpoints', slug: 'reference/api-endpoints' },
            { label: 'CLI Commands', slug: 'reference/cli-commands' },
          ],
        },
      ],
      editLink: {
        baseUrl: 'https://github.com/monaccode/astromech-platform/edit/develop/docs-site/',
      },
      customCss: ['./src/styles/custom.css'],
    }),
  ],
});
```

**Step 4: Create `tsconfig.json`**

```json
{
  "extends": "astro/tsconfigs/strict"
}
```

**Step 5: Create content config**

Create `docs-site/src/content/config.ts`:

```ts
import { defineCollection } from 'astro:content';
import { docsSchema } from '@astrojs/starlight/schema';

export const collections = {
  docs: defineCollection({ schema: docsSchema() }),
};
```

**Step 6: Create custom CSS stub**

Create `docs-site/src/styles/custom.css`:

```css
/* Astromesh documentation custom styles */

:root {
  --sl-color-accent-low: #1a1a2e;
  --sl-color-accent: #4361ee;
  --sl-color-accent-high: #b8c0ff;
  --sl-font-system: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
```

**Step 7: Verify build**

```bash
cd docs-site && npm run build
```

Expected: Build succeeds (may warn about missing content, that's OK).

**Step 8: Commit**

```bash
git add docs-site/
git commit -m "feat(docs-site): scaffold Starlight project with sidebar config"
```

---

## Task 2: Interactive Components — PipelineDiagram

**Files:**
- Create: `docs-site/src/components/PipelineDiagram.astro`

**Step 1: Create the pipeline diagram component**

This component renders the 7-step agent execution pipeline as an animated SVG/HTML diagram. Each step is a node that highlights on hover with a tooltip. On page load, steps animate left-to-right sequentially.

```astro
---
// PipelineDiagram.astro
// Animated agent execution pipeline diagram
const steps = [
  { name: 'Query', icon: '📥', desc: 'User sends a query to the agent via REST API or WebSocket' },
  { name: 'Input Guardrails', icon: '🛡️', desc: 'PII detection, max length check, topic filtering on input' },
  { name: 'Prompt Engine', icon: '📝', desc: 'Jinja2 renders the system prompt with memory context and variables' },
  { name: 'Model Router', icon: '🔀', desc: 'Routes to the best provider using cost, latency, or quality strategy' },
  { name: 'Tool Calls', icon: '🔧', desc: 'Executes tools (internal, MCP, webhook, RAG) as directed by the LLM' },
  { name: 'Output Guardrails', icon: '🔒', desc: 'Content filter, cost limit, PII redaction on output' },
  { name: 'Response', icon: '📤', desc: 'Final response returned to the caller and persisted to memory' },
];
---

<div class="pipeline-container">
  <div class="pipeline-track">
    {steps.map((step, i) => (
      <div class="pipeline-step" style={`--step-index: ${i}`}>
        <div class="step-node" tabindex="0">
          <span class="step-icon">{step.icon}</span>
          <span class="step-name">{step.name}</span>
          <div class="step-tooltip">{step.desc}</div>
        </div>
        {i < steps.length - 1 && <div class="step-arrow">→</div>}
      </div>
    ))}
  </div>
</div>

<style>
  .pipeline-container {
    overflow-x: auto;
    padding: 2rem 0;
    margin: 1.5rem 0;
  }

  .pipeline-track {
    display: flex;
    align-items: center;
    gap: 0;
    min-width: max-content;
    padding: 1rem;
  }

  .pipeline-step {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    opacity: 0;
    transform: translateY(10px);
    animation: stepFadeIn 0.4s ease forwards;
    animation-delay: calc(var(--step-index) * 0.15s);
  }

  .step-node {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.4rem;
    padding: 0.8rem 1rem;
    border: 2px solid var(--sl-color-accent);
    border-radius: 10px;
    background: var(--sl-color-bg-nav);
    cursor: pointer;
    transition: all 0.2s ease;
    min-width: 7rem;
    text-align: center;
  }

  .step-node:hover,
  .step-node:focus {
    border-color: var(--sl-color-accent-high);
    background: var(--sl-color-accent-low);
    transform: translateY(-4px);
    box-shadow: 0 4px 12px rgba(67, 97, 238, 0.3);
  }

  .step-icon {
    font-size: 1.5rem;
  }

  .step-name {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--sl-color-text);
    white-space: nowrap;
  }

  .step-tooltip {
    position: absolute;
    bottom: calc(100% + 0.75rem);
    left: 50%;
    transform: translateX(-50%);
    padding: 0.6rem 0.8rem;
    background: var(--sl-color-bg);
    border: 1px solid var(--sl-color-gray-5);
    border-radius: 6px;
    font-size: 0.75rem;
    color: var(--sl-color-text);
    white-space: normal;
    width: 14rem;
    text-align: center;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.2s;
    z-index: 10;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  }

  .step-node:hover .step-tooltip,
  .step-node:focus .step-tooltip {
    opacity: 1;
  }

  .step-arrow {
    font-size: 1.2rem;
    color: var(--sl-color-accent);
    margin: 0 0.25rem;
    opacity: 0;
    animation: stepFadeIn 0.3s ease forwards;
    animation-delay: calc(var(--step-index) * 0.15s + 0.1s);
  }

  @keyframes stepFadeIn {
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  @media (max-width: 768px) {
    .pipeline-track {
      flex-direction: column;
      min-width: auto;
    }
    .step-arrow {
      transform: rotate(90deg);
    }
    .step-tooltip {
      left: calc(100% + 0.75rem);
      bottom: auto;
      transform: none;
    }
  }
</style>
```

**Step 2: Verify component renders**

Create a temporary test page at `docs-site/src/content/docs/test.mdx`:

```mdx
---
title: Component Test
---
import PipelineDiagram from '../../components/PipelineDiagram.astro';

<PipelineDiagram />
```

Run: `cd docs-site && npm run dev` — open `http://localhost:4321/astromech-platform/test/` and verify the pipeline renders with animation.

**Step 3: Commit**

```bash
git add docs-site/src/components/PipelineDiagram.astro
git commit -m "feat(docs-site): add PipelineDiagram interactive component"
```

---

## Task 3: Interactive Components — FeatureCards

**Files:**
- Create: `docs-site/src/components/FeatureCards.astro`

**Step 1: Create the feature cards component**

Grid of 6 expandable cards. Uses native `<details>` for expand/collapse (no JS needed, accessible by default).

```astro
---
// FeatureCards.astro
const features = [
  {
    title: '6 LLM Providers',
    icon: '🤖',
    summary: 'Connect to any model, local or cloud',
    details: 'Ollama, OpenAI-compatible, vLLM, llama.cpp, HuggingFace TGI, ONNX Runtime. Automatic failover with circuit breaker (3 failures → 60s cooldown).',
  },
  {
    title: '6 Orchestration Patterns',
    icon: '🔄',
    summary: 'From simple to multi-agent',
    details: 'ReAct (think-act-observe), Plan & Execute, Parallel Fan-Out, Pipeline, Supervisor (delegate to workers), Swarm (agents hand off conversations).',
  },
  {
    title: '3 Memory Types',
    icon: '🧠',
    summary: 'Persistent context across conversations',
    details: 'Conversational (Redis/PG/SQLite), Semantic (pgvector/ChromaDB/Qdrant/FAISS), Episodic (PostgreSQL). Strategies: sliding window, summary, token budget.',
  },
  {
    title: 'RAG Pipeline',
    icon: '📚',
    summary: 'Document ingestion to retrieval',
    details: '4 chunking strategies (fixed, recursive, sentence, semantic), 3 embedding providers, 4 vector stores, 2 rerankers (cross-encoder, Cohere).',
  },
  {
    title: 'Mesh Discovery (Maia)',
    icon: '🌐',
    summary: 'Nodes find each other automatically',
    details: 'Gossip-based discovery, failure detection (alive→suspect→dead), leader election, least-connections routing. No manual peer configuration.',
  },
  {
    title: 'Rust Extensions',
    icon: '⚡',
    summary: '5-50x speedup on CPU-bound paths',
    details: 'Optional native Rust extensions via PyO3 for chunking, PII detection, tokenization, rate limiting. Pure Python fallback when not compiled.',
  },
];
---

<div class="features-grid">
  {features.map((feature) => (
    <details class="feature-card">
      <summary class="feature-summary">
        <span class="feature-icon">{feature.icon}</span>
        <div class="feature-text">
          <span class="feature-title">{feature.title}</span>
          <span class="feature-subtitle">{feature.summary}</span>
        </div>
        <span class="feature-chevron">▸</span>
      </summary>
      <div class="feature-details">
        <p>{feature.details}</p>
      </div>
    </details>
  ))}
</div>

<style>
  .features-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1rem;
    margin: 2rem 0;
  }

  .feature-card {
    border: 1px solid var(--sl-color-gray-5);
    border-radius: 10px;
    background: var(--sl-color-bg-nav);
    overflow: hidden;
    transition: border-color 0.2s;
  }

  .feature-card:hover {
    border-color: var(--sl-color-accent);
  }

  .feature-card[open] {
    border-color: var(--sl-color-accent);
  }

  .feature-summary {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1rem;
    cursor: pointer;
    list-style: none;
  }

  .feature-summary::-webkit-details-marker {
    display: none;
  }

  .feature-icon {
    font-size: 1.75rem;
    flex-shrink: 0;
  }

  .feature-text {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }

  .feature-title {
    font-weight: 700;
    font-size: 0.95rem;
    color: var(--sl-color-text);
  }

  .feature-subtitle {
    font-size: 0.8rem;
    color: var(--sl-color-gray-3);
  }

  .feature-chevron {
    font-size: 1rem;
    color: var(--sl-color-gray-3);
    transition: transform 0.2s;
  }

  .feature-card[open] .feature-chevron {
    transform: rotate(90deg);
  }

  .feature-details {
    padding: 0 1rem 1rem;
    font-size: 0.85rem;
    color: var(--sl-color-gray-2);
    line-height: 1.5;
  }

  .feature-details p {
    margin: 0;
  }
</style>
```

**Step 2: Commit**

```bash
git add docs-site/src/components/FeatureCards.astro
git commit -m "feat(docs-site): add FeatureCards expandable component"
```

---

## Task 4: Interactive Components — DeploymentTabs

**Files:**
- Create: `docs-site/src/components/DeploymentTabs.astro`

**Step 1: Create the deployment tabs component**

Tab switcher showing installation snippets for each deployment mode. Uses a small inline `<script>` for tab switching (Astro island).

```astro
---
// DeploymentTabs.astro
const tabs = [
  {
    id: 'standalone',
    label: 'Standalone',
    code: `git clone https://github.com/monaccode/astromech-platform.git
cd astromech-platform
uv sync --extra all
astromeshctl init --dev
astromeshd --config ./config`,
  },
  {
    id: 'os',
    label: 'Astromesh OS',
    code: `# Add APT repository
curl -fsSL https://monaccode.github.io/astromech-platform/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/astromesh.gpg
echo "deb [signed-by=/usr/share/keyrings/astromesh.gpg] https://monaccode.github.io/astromech-platform stable main" | sudo tee /etc/apt/sources.list.d/astromesh.list

# Install and start
sudo apt update && sudo apt install astromesh
sudo astromeshctl init
sudo systemctl enable --now astromeshd`,
  },
  {
    id: 'docker',
    label: 'Docker',
    code: `# Single node with Ollama
docker compose -f recipes/single-node.yml up -d
curl http://localhost:8000/v1/health`,
  },
  {
    id: 'maia',
    label: 'Maia Mesh',
    code: `# 3-node mesh: gateway + worker + inference
docker compose -f recipes/mesh-3node.yml up -d
curl http://localhost:8000/v1/mesh/state`,
  },
  {
    id: 'maia-gpu',
    label: 'Maia + GPU',
    code: `# Mesh with NVIDIA GPU inference
docker compose -f recipes/mesh-gpu.yml up -d`,
  },
  {
    id: 'helm',
    label: 'Helm',
    code: `cd deploy/helm/astromesh
helm dependency update
helm install astromesh . -f values-dev.yaml \\
  --namespace astromesh --create-namespace
kubectl get pods -n astromesh`,
  },
  {
    id: 'argocd',
    label: 'ArgoCD',
    code: `# Multi-environment GitOps deployment
kubectl apply -f deploy/gitops/argocd/applicationset.yaml
# Creates: astromesh-dev, astromesh-staging, astromesh-prod`,
  },
];
---

<div class="deploy-tabs" id="deploy-tabs">
  <div class="tab-bar" role="tablist">
    {tabs.map((tab, i) => (
      <button
        role="tab"
        class={`tab-button ${i === 0 ? 'active' : ''}`}
        data-tab={tab.id}
        aria-selected={i === 0 ? 'true' : 'false'}
      >
        {tab.label}
      </button>
    ))}
  </div>
  <div class="tab-panels">
    {tabs.map((tab, i) => (
      <div
        class={`tab-panel ${i === 0 ? 'active' : ''}`}
        data-panel={tab.id}
        role="tabpanel"
      >
        <div class="code-block">
          <button class="copy-btn" data-code={tab.code} aria-label="Copy to clipboard">
            Copy
          </button>
          <pre><code>{tab.code}</code></pre>
        </div>
      </div>
    ))}
  </div>
</div>

<script>
  document.addEventListener('astro:page-load', () => {
    const container = document.getElementById('deploy-tabs');
    if (!container) return;

    container.querySelectorAll('.tab-button').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tabId = btn.getAttribute('data-tab');
        container.querySelectorAll('.tab-button').forEach((b) => {
          b.classList.remove('active');
          b.setAttribute('aria-selected', 'false');
        });
        container.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
        btn.classList.add('active');
        btn.setAttribute('aria-selected', 'true');
        container.querySelector(`[data-panel="${tabId}"]`)?.classList.add('active');
      });
    });

    container.querySelectorAll('.copy-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const code = btn.getAttribute('data-code') || '';
        navigator.clipboard.writeText(code).then(() => {
          btn.textContent = 'Copied!';
          setTimeout(() => (btn.textContent = 'Copy'), 2000);
        });
      });
    });
  });
</script>

<style>
  .deploy-tabs {
    margin: 2rem 0;
    border: 1px solid var(--sl-color-gray-5);
    border-radius: 10px;
    overflow: hidden;
  }

  .tab-bar {
    display: flex;
    overflow-x: auto;
    background: var(--sl-color-bg-nav);
    border-bottom: 1px solid var(--sl-color-gray-5);
    gap: 0;
  }

  .tab-button {
    padding: 0.6rem 1rem;
    border: none;
    background: transparent;
    color: var(--sl-color-gray-3);
    cursor: pointer;
    font-size: 0.85rem;
    font-weight: 500;
    white-space: nowrap;
    border-bottom: 2px solid transparent;
    transition: all 0.2s;
  }

  .tab-button:hover {
    color: var(--sl-color-text);
    background: var(--sl-color-accent-low);
  }

  .tab-button.active {
    color: var(--sl-color-accent);
    border-bottom-color: var(--sl-color-accent);
  }

  .tab-panel {
    display: none;
    padding: 0;
  }

  .tab-panel.active {
    display: block;
  }

  .code-block {
    position: relative;
  }

  .code-block pre {
    margin: 0;
    padding: 1.25rem;
    overflow-x: auto;
    background: var(--sl-color-bg);
    font-size: 0.85rem;
    line-height: 1.6;
  }

  .code-block code {
    font-family: var(--sl-font-mono);
  }

  .copy-btn {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    padding: 0.25rem 0.6rem;
    border: 1px solid var(--sl-color-gray-5);
    border-radius: 4px;
    background: var(--sl-color-bg-nav);
    color: var(--sl-color-gray-3);
    font-size: 0.75rem;
    cursor: pointer;
    transition: all 0.2s;
  }

  .copy-btn:hover {
    border-color: var(--sl-color-accent);
    color: var(--sl-color-accent);
  }
</style>
```

**Step 2: Commit**

```bash
git add docs-site/src/components/DeploymentTabs.astro
git commit -m "feat(docs-site): add DeploymentTabs interactive component"
```

---

## Task 5: Interactive Components — AgentExample

**Files:**
- Create: `docs-site/src/components/AgentExample.astro`

**Step 1: Create the agent example split-pane component**

Side-by-side view: agent YAML on the left, curl command + response on the right.

```astro
---
// AgentExample.astro
const yamlCode = `apiVersion: astromesh/v1
kind: Agent
metadata:
  name: hello-agent

spec:
  identity:
    description: A minimal test agent

  model:
    primary:
      provider: ollama
      model: llama3.1:8b
      endpoint: http://ollama:11434
      parameters:
        temperature: 0.7

  prompts:
    system: |
      You are a helpful assistant.
      Keep responses brief.

  orchestration:
    pattern: react
    max_iterations: 3`;

const curlCode = `curl -X POST http://localhost:8000/v1/agents/hello-agent/run \\
  -H "Content-Type: application/json" \\
  -d '{"query": "What is 2+2?", "session_id": "demo"}'`;

const responseCode = `{
  "agent": "hello-agent",
  "response": "2 + 2 = 4",
  "session_id": "demo",
  "tokens_used": 42,
  "provider": "ollama",
  "pattern": "react",
  "iterations": 1
}`;
---

<div class="agent-example">
  <div class="example-pane">
    <div class="pane-header">
      <span class="pane-label">config/agents/hello.agent.yaml</span>
      <button class="copy-btn" data-code={yamlCode} aria-label="Copy YAML">Copy</button>
    </div>
    <pre class="pane-code"><code>{yamlCode}</code></pre>
  </div>
  <div class="example-pane">
    <div class="pane-header">
      <span class="pane-label">Try it</span>
      <button class="copy-btn" data-code={curlCode} aria-label="Copy curl">Copy</button>
    </div>
    <pre class="pane-code"><code>{curlCode}</code></pre>
    <div class="pane-header response-header">
      <span class="pane-label">Response</span>
    </div>
    <pre class="pane-code response"><code>{responseCode}</code></pre>
  </div>
</div>

<script>
  document.addEventListener('astro:page-load', () => {
    document.querySelectorAll('.agent-example .copy-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const code = btn.getAttribute('data-code') || '';
        navigator.clipboard.writeText(code).then(() => {
          btn.textContent = 'Copied!';
          setTimeout(() => (btn.textContent = 'Copy'), 2000);
        });
      });
    });
  });
</script>

<style>
  .agent-example {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
    margin: 2rem 0;
  }

  @media (max-width: 768px) {
    .agent-example {
      grid-template-columns: 1fr;
    }
  }

  .example-pane {
    border: 1px solid var(--sl-color-gray-5);
    border-radius: 10px;
    overflow: hidden;
  }

  .pane-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0.75rem;
    background: var(--sl-color-bg-nav);
    border-bottom: 1px solid var(--sl-color-gray-5);
  }

  .response-header {
    border-top: 1px solid var(--sl-color-gray-5);
  }

  .pane-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--sl-color-gray-3);
    font-family: var(--sl-font-mono);
  }

  .pane-code {
    margin: 0;
    padding: 1rem;
    overflow-x: auto;
    font-size: 0.8rem;
    line-height: 1.5;
    background: var(--sl-color-bg);
  }

  .pane-code code {
    font-family: var(--sl-font-mono);
  }

  .pane-code.response {
    background: var(--sl-color-accent-low);
  }

  .copy-btn {
    padding: 0.2rem 0.5rem;
    border: 1px solid var(--sl-color-gray-5);
    border-radius: 4px;
    background: transparent;
    color: var(--sl-color-gray-3);
    font-size: 0.7rem;
    cursor: pointer;
    transition: all 0.2s;
  }

  .copy-btn:hover {
    border-color: var(--sl-color-accent);
    color: var(--sl-color-accent);
  }
</style>
```

**Step 2: Commit**

```bash
git add docs-site/src/components/AgentExample.astro
git commit -m "feat(docs-site): add AgentExample split-pane component"
```

---

## Task 6: Landing Page

**Files:**
- Create: `docs-site/src/content/docs/index.mdx`

**Step 1: Create the interactive landing page**

```mdx
---
title: Astromesh
description: AI Agent Runtime Platform
template: splash
hero:
  title: Astromesh
  tagline: Multi-model, multi-pattern AI agent runtime with declarative YAML configuration.
  actions:
    - text: Get Started
      link: /astromech-platform/getting-started/what-is-astromesh/
      icon: right-arrow
      variant: primary
    - text: View on GitHub
      link: https://github.com/monaccode/astromech-platform
      icon: external
      variant: minimal
---

import PipelineDiagram from '../../components/PipelineDiagram.astro';
import FeatureCards from '../../components/FeatureCards.astro';
import DeploymentTabs from '../../components/DeploymentTabs.astro';
import AgentExample from '../../components/AgentExample.astro';

## Agent Execution Pipeline

Define agents in YAML. Astromesh handles the rest — from input safety checks to model routing to tool execution.

<PipelineDiagram />

## Features

Everything you need to build, deploy, and scale AI agents.

<FeatureCards />

## Deploy Your Way

From a single command to a production Kubernetes cluster.

<DeploymentTabs />

## Define an Agent in 20 Lines

Create a YAML file, start the daemon, call the API.

<AgentExample />
```

**Step 2: Verify landing page**

Run: `cd docs-site && npm run dev`

Open `http://localhost:4321/astromech-platform/` and verify:
- Hero section renders with title, tagline, buttons
- Pipeline diagram animates sequentially
- Feature cards expand/collapse on click
- Deployment tabs switch between snippets with copy buttons
- Agent example shows split pane

**Step 3: Commit**

```bash
git add docs-site/src/content/docs/index.mdx
git commit -m "feat(docs-site): add interactive landing page with all components"
```

---

## Task 7: Getting Started Pages

**Files:**
- Create: `docs-site/src/content/docs/getting-started/what-is-astromesh.md`
- Create: `docs-site/src/content/docs/getting-started/installation.md`
- Create: `docs-site/src/content/docs/getting-started/quickstart.md`
- Create: `docs-site/src/content/docs/getting-started/first-agent.md`

**Step 1: Create all 4 pages**

Content sources and expansion:
- `what-is-astromesh.md` — Based on `TECH_OVERVIEW.md` intro + `README.md` features list. Expand with: what problem it solves, who it's for, key concepts (agents, providers, orchestration patterns), how layers relate. Include the 4-layer ASCII diagram from `GENERAL_ARCHITECTURE.md`.
- `installation.md` — Merge `INSTALLATION.md` (APT) + `README.md` quick start (uv sync). Cover: Python 3.12+ check, uv install, `uv sync` with extras table, Docker image pull (`docker pull monaccode/astromesh:latest`), APT install. Each method as a subsection.
- `quickstart.md` — Based on `DEV_QUICKSTART.md`. Expand: step-by-step from clone to running agent, verify health, see response. Include expected output at each step.
- `first-agent.md` — Based on `README.md` "Create Your First Agent" + `CONFIGURATION_GUIDE.md` minimal agent. Expand: explain each YAML field, create the file, start daemon, call API, see response, modify temperature and observe difference, add a tool, add memory. Progressive complexity.

Each page frontmatter:

```yaml
---
title: <Title>
description: <One line>
---
```

**Step 2: Verify build**

Run: `cd docs-site && npm run build`
Expected: Build succeeds, pages accessible in sidebar.

**Step 3: Commit**

```bash
git add docs-site/src/content/docs/getting-started/
git commit -m "feat(docs-site): add Getting Started section (4 pages)"
```

---

## Task 8: Architecture Pages

**Files:**
- Create: `docs-site/src/content/docs/architecture/overview.md`
- Create: `docs-site/src/content/docs/architecture/four-layer-design.md`
- Create: `docs-site/src/content/docs/architecture/agent-pipeline.md`
- Create: `docs-site/src/content/docs/architecture/k8s-architecture.md`

**Step 1: Create all 4 pages**

Content sources:
- `overview.md` — Based on `TECH_OVERVIEW.md`. High-level feature overview with the 4-layer diagram. Include project structure tree from `README.md`.
- `four-layer-design.md` — Full content from `GENERAL_ARCHITECTURE.md`. Expand each layer with code file references, class/protocol names, and how they connect. Include all ASCII diagrams.
- `agent-pipeline.md` — Based on `GENERAL_ARCHITECTURE.md` "Agent Execution Flow" section. Expand each pipeline step (query → guardrails → memory → prompt → orchestration → model → tools → guardrails → persist → response) with what happens, which class handles it, what config controls it.
- `k8s-architecture.md` — Full content from `K8S_ARCHITECTURE.md`. CRDs, operator design, control/data plane diagrams.

**Step 2: Commit**

```bash
git add docs-site/src/content/docs/architecture/
git commit -m "feat(docs-site): add Architecture section (4 pages)"
```

---

## Task 9: Configuration Pages

**Files:**
- Create: `docs-site/src/content/docs/configuration/init-wizard.md`
- Create: `docs-site/src/content/docs/configuration/agent-yaml.md`
- Create: `docs-site/src/content/docs/configuration/providers.md`
- Create: `docs-site/src/content/docs/configuration/runtime-config.md`
- Create: `docs-site/src/content/docs/configuration/profiles.md`
- Create: `docs-site/src/content/docs/configuration/channels.md`

**Step 1: Create all 6 pages**

Content sources:
- `init-wizard.md` — Based on `DEV_QUICKSTART.md` "Using the Init Wizard" section + `ASTROMESH_OS.md`. Expand: document every wizard question/prompt with explanation, what each answer generates, `--non-interactive` flags, `--dev` vs production mode. Show the generated files after each wizard choice.
- `agent-yaml.md` — Full content from `CONFIGURATION_GUIDE.md` Agent section. Include minimal agent + full reference. Expand: every field documented with type, default, valid values, and example. Group by section (identity, model, prompts, orchestration, tools, memory, guardrails, permissions).
- `providers.md` — Full content from `CONFIGURATION_GUIDE.md` Provider section. Expand: each provider type with setup instructions (how to install/run the backend), example config, common pitfalls. Include routing strategies table and circuit breaker explanation.
- `runtime-config.md` — Full content from `CONFIGURATION_GUIDE.md` Runtime section. Expand: every field, services toggle map, defaults section, env var override patterns. Include `ASTROMESH_CONFIG_DIR` usage.
- `profiles.md` — Based on `ASTROMESH_NODES.md` profiles table + profile YAML files in `config/profiles/`. Document all 7 profiles: what services each enables, when to use each, how to customize. Show the actual YAML content of each profile. Explain how the Docker entrypoint selects profiles.
- `channels.md` — Full content from `CONFIGURATION_GUIDE.md` Channel section + `WHATSAPP_INTEGRATION.md` config section. Expand: WhatsApp setup from Meta Business account to working webhook. Env vars table. Rate limiting explanation.

**Step 2: Commit**

```bash
git add docs-site/src/content/docs/configuration/
git commit -m "feat(docs-site): add Configuration section (6 pages)"
```

---

## Task 10: Deployment — Standalone & Astromesh OS

**Files:**
- Create: `docs-site/src/content/docs/deployment/standalone.md`
- Create: `docs-site/src/content/docs/deployment/astromesh-os.md`

**Step 1: Create standalone guide**

Based on `DEV_QUICKSTART.md` + `README.md`. Sections:

1. What & Why — running from source for development
2. Prerequisites — Python 3.12+, uv, Git, (optional) Docker for Ollama
3. Clone & Install — `git clone`, `uv sync --extra all`, extras table
4. Configure Providers — set `OPENAI_API_KEY` or start Ollama
5. Init Wizard — `astromeshctl init --dev`, explain each step
6. Start the Server — `uv run uvicorn` and `astromeshd` options
7. Verify — health check, list agents, run agent with curl
8. Development Workflow — `--reload`, running tests, linting
9. Troubleshooting — port in use, Ollama not running, Python version mismatch

**Step 2: Create Astromesh OS guide**

Based on `ASTROMESH_OS.md` + `INSTALLATION.md` + `ASTROMESH_NODES.md`. Sections:

1. What & Why — daemon + systemd for production Linux servers
2. Prerequisites — Ubuntu/Debian, systemd
3. Install via APT — add repo, install package, verify
4. Init Wizard — `sudo astromeshctl init`, each question documented
5. Profiles — which profile was selected, what services it enables
6. systemd Service — `systemctl enable/start`, status, logs
7. Configuration — `/etc/astromesh/` layout, editing runtime.yaml, providers.yaml
8. CLI Operations — `astromeshctl status`, `doctor`, `agents list`, `providers list`, `config validate`, `--json` flag
9. Multi-Node with Nodes — setting up gateway + worker + inference on separate machines, configuring peers
10. Upgrading — `apt update && apt upgrade`, migration notes
11. Uninstalling — `apt remove`, cleanup
12. Troubleshooting — service won't start, permission errors, config validation failures

**Step 3: Commit**

```bash
git add docs-site/src/content/docs/deployment/standalone.md docs-site/src/content/docs/deployment/astromesh-os.md
git commit -m "feat(docs-site): add Standalone and Astromesh OS deployment guides"
```

---

## Task 11: Deployment — Docker Single Node

**Files:**
- Create: `docs-site/src/content/docs/deployment/docker-single.md`

**Step 1: Create Docker single node guide**

Based on `recipes/single-node.yml` + Docker entrypoint. Sections:

1. What & Why — pre-built image, no source checkout needed
2. Prerequisites — Docker, Docker Compose
3. Quick Start — `docker compose -f recipes/single-node.yml up -d`, verify health
4. Image & Entrypoint — how `monaccode/astromesh:latest` works, entrypoint env var → config generation
5. Environment Variables — full table (ASTROMESH_ROLE, PORT, OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)
6. Adding Providers — setting API keys as env vars in compose
7. Custom Agents — mounting agent YAML files via volumes
8. Connecting Ollama — how the astromesh container talks to ollama container, OLLAMA_HOST
9. Persistent Data — volumes for Ollama models, what data persists
10. Custom Config — mounting runtime.yaml, `ASTROMESH_AUTO_CONFIG=false`
11. Monitoring — adding prometheus/grafana, reference to dev-full recipe
12. Troubleshooting — container won't start, health check failing, Ollama connection refused

**Step 2: Commit**

```bash
git add docs-site/src/content/docs/deployment/docker-single.md
git commit -m "feat(docs-site): add Docker Single Node deployment guide"
```

---

## Task 12: Deployment — Docker Maia & Docker Maia + GPU

**Files:**
- Create: `docs-site/src/content/docs/deployment/docker-maia.md`
- Create: `docs-site/src/content/docs/deployment/docker-maia-gpu.md`

**Step 1: Create Docker Maia guide**

Based on `MAIA_GUIDE.md` + `ASTROMESH_MAIA.md` + `recipes/mesh-3node.yml`. Sections:

1. What & Why — gossip-based mesh, automatic discovery vs static peers
2. Prerequisites — Docker, Docker Compose
3. Understanding Roles — gateway (API entry point, no agents), worker (agent execution), inference (LLM serving)
4. Quick Start — `docker compose -f recipes/mesh-3node.yml up -d`
5. Verify the Mesh — `curl localhost:8000/v1/mesh/state`, expected output with 3 nodes
6. How It Works — entrypoint generates mesh profiles, gossip connects nodes
7. Environment Variables — full table with mesh-specific vars (ASTROMESH_MESH_ENABLED, ASTROMESH_SEEDS, ASTROMESH_NODE_NAME)
8. Scaling Workers — `--scale worker=3`, auto-registration
9. Adding API Keys — env vars in compose for cloud providers
10. Custom Agents — mounting agent YAMLs on worker nodes
11. Infrastructure Services — Redis (shared state), PostgreSQL (pgvector for RAG/memory)
12. CLI in Docker — `docker exec` commands for mesh status, nodes, leave
13. Maia vs Static Peers — comparison table
14. Troubleshooting — nodes not discovering, suspect/dead states, seeds misconfigured

**Step 2: Create Docker Maia + GPU guide**

Based on `recipes/mesh-gpu.yml`. Sections:

1. What & Why — GPU-accelerated inference in mesh mode
2. Prerequisites — NVIDIA GPU with drivers, NVIDIA Container Toolkit
3. Verify GPU Setup — `nvidia-smi`, Docker GPU test
4. Quick Start — `docker compose -f recipes/mesh-gpu.yml up -d`
5. How GPU Is Assigned — Ollama container gets GPU reservation, inference node routes to it
6. Running Large Models — `docker exec ollama ollama pull llama3.1:70b`
7. Multi-GPU Setup — adjusting `count` in deploy resources
8. Troubleshooting — GPU not detected, CUDA errors, OOM

**Step 3: Commit**

```bash
git add docs-site/src/content/docs/deployment/docker-maia.md docs-site/src/content/docs/deployment/docker-maia-gpu.md
git commit -m "feat(docs-site): add Docker Maia and Maia+GPU deployment guides"
```

---

## Task 13: Deployment — Helm/Kubernetes & ArgoCD

**Files:**
- Create: `docs-site/src/content/docs/deployment/helm-kubernetes.md`
- Create: `docs-site/src/content/docs/deployment/argocd-gitops.md`

**Step 1: Create Helm/Kubernetes guide**

Based on `KUBERNETES_DEPLOYMENT.md`. Sections:

1. What & Why — production Kubernetes deployment with Helm
2. Prerequisites — K8s 1.26+, Helm 3, kubectl, container registry
3. Chart Overview — structure, dependencies table
4. Quick Start — dependency update, install with values-dev.yaml, verify pods
5. Configuration — inline config (runtime, providers, agents, channels in values.yaml)
6. Secrets Management — inline (dev) vs existing secret (prod)
7. External Database — disabling bundled PG, connecting to RDS/Cloud SQL
8. External Redis — disabling bundled Redis, connecting to ElastiCache
9. Model Serving — vLLM setup (GPU, model selection, HF token), TEI instances (embeddings + reranker)
10. GPU Scheduling — nodeSelector, tolerations, resource requests
11. Observability — Prometheus annotations, OTel endpoint (manual + auto-wired), full stack with kube-prometheus-stack
12. Ingress — nginx example with cert-manager TLS
13. Autoscaling — HPA configuration
14. Environment Profiles — dev vs staging vs prod values comparison table
15. External Secrets (ESO) — SecretStore + ExternalSecret setup, AWS/GCP/Vault examples
16. CRDs — all 4 CRDs documented with kubectl examples
17. Useful Commands — install, upgrade, dry-run, lint, uninstall, status
18. Production Checklist — security, HA, backup, monitoring

**Step 2: Create ArgoCD guide**

Based on `KUBERNETES_DEPLOYMENT.md` GitOps section + `deploy/gitops/argocd/applicationset.yaml`. Sections:

1. What & Why — GitOps workflow, automated sync
2. Prerequisites — ArgoCD installed, repo accessible
3. Deploy the ApplicationSet — `kubectl apply`, what it creates
4. Environments — dev/staging/prod table with namespace, values file, auto-sync
5. Workflow — push → ArgoCD detects → sync → rolling update
6. Customizing — modifying applicationset.yaml, adding environments
7. Promotion — how to promote changes from dev to staging to prod
8. Rollback — ArgoCD rollback commands and UI
9. Troubleshooting — sync failures, secret issues, drift detection

**Step 3: Commit**

```bash
git add docs-site/src/content/docs/deployment/helm-kubernetes.md docs-site/src/content/docs/deployment/argocd-gitops.md
git commit -m "feat(docs-site): add Helm/Kubernetes and ArgoCD deployment guides"
```

---

## Task 14: Advanced Pages

**Files:**
- Create: `docs-site/src/content/docs/advanced/rust-extensions.md`
- Create: `docs-site/src/content/docs/advanced/whatsapp.md`
- Create: `docs-site/src/content/docs/advanced/observability.md`
- Create: `docs-site/src/content/docs/advanced/maia-internals.md`

**Step 1: Create all 4 pages**

Content sources:
- `rust-extensions.md` — Based on `NATIVE_ESTENSIONS_RUST.md`. Expand: what gets optimized (chunking, PII, tokenization, rate limiting), benchmark numbers, install Rust + maturin, build extensions, verify with `ASTROMESH_FORCE_PYTHON=1` toggle, CI integration.
- `whatsapp.md` — Full content from `WHATSAPP_INTEGRATION.md`. Expand: Meta Business account setup, app creation, webhook URL configuration, environment variables, agent YAML for WhatsApp, testing with ngrok, production deployment, message types supported, rate limiting, troubleshooting.
- `observability.md` — Based on `GENERAL_ARCHITECTURE.md` observability section + docker-compose.yaml monitoring services. Expand: OpenTelemetry setup (tracing, spans), Prometheus metrics (what metrics are exposed, PromQL examples), Grafana dashboards, cost tracking (budget alerts), Docker monitoring stack setup, Kubernetes monitoring with kube-prometheus-stack.
- `maia-internals.md` — Based on `ASTROMESH_MAIA.md` protocol sections. Expand: gossip algorithm details, heartbeat timing, failure detection thresholds, bully leader election, request routing (least-connections), API endpoints for debugging, backward compatibility notes, limitations.

**Step 2: Commit**

```bash
git add docs-site/src/content/docs/advanced/
git commit -m "feat(docs-site): add Advanced section (4 pages)"
```

---

## Task 15: Reference Pages — Core

**Files:**
- Create: `docs-site/src/content/docs/reference/core/runtime-engine.md`
- Create: `docs-site/src/content/docs/reference/core/model-router.md`
- Create: `docs-site/src/content/docs/reference/core/tool-registry.md`
- Create: `docs-site/src/content/docs/reference/core/memory-manager.md`

**Step 1: Create all 4 pages**

Content sources — all from `GENERAL_ARCHITECTURE.md` Layer 2-3 sections:
- `runtime-engine.md` — AgentRuntime class, bootstrap flow, YAML loading, agent lifecycle, `runtime.run()` API. Include configuration loading flow diagram.
- `model-router.md` — ModelRouter class, routing strategies table (with when to use each), circuit breaker parameters, provider protocol methods, fallback behavior. Include ASCII routing diagram.
- `tool-registry.md` — ToolRegistry class, 4 tool types (internal, MCP, webhook, RAG), registration, permissions, rate limiting, schema generation for function calling. Include MCP client/server details.
- `memory-manager.md` — MemoryManager class, 3 memory types with backend options, 3 strategies with configuration, `build_context()` and `persist_turn()` flows. Include memory backends diagram.

**Step 2: Commit**

```bash
git add docs-site/src/content/docs/reference/core/
git commit -m "feat(docs-site): add Reference/Core section (4 pages)"
```

---

## Task 16: Reference Pages — OS, Mesh, and Consolidated

**Files:**
- Create: `docs-site/src/content/docs/reference/os/daemon.md`
- Create: `docs-site/src/content/docs/reference/os/cli.md`
- Create: `docs-site/src/content/docs/reference/mesh/gossip-protocol.md`
- Create: `docs-site/src/content/docs/reference/mesh/scheduling.md`
- Create: `docs-site/src/content/docs/reference/env-vars.md`
- Create: `docs-site/src/content/docs/reference/api-endpoints.md`
- Create: `docs-site/src/content/docs/reference/cli-commands.md`

**Step 1: Create all 7 pages**

Content sources:
- `daemon.md` — Based on `ASTROMESH_OS.md` daemon section. Config auto-detection table, startup sequence, PID file, systemd integration, CLI flags (`--config`, `--port`, `--log-level`).
- `cli.md` — Based on `ASTROMESH_OS.md` CLI section + mesh CLI from `ASTROMESH_MAIA.md`. Every command documented: `status`, `doctor`, `agents list`, `providers list`, `config validate`, `services`, `peers list`, `mesh status`, `mesh nodes`, `mesh leave`, `init`. Include `--json` output examples.
- `gossip-protocol.md` — Based on `ASTROMESH_MAIA.md` gossip sections. Push-pull gossip algorithm, heartbeat intervals, failure detection thresholds, state convergence, ASCII sequence diagrams.
- `scheduling.md` — Based on `ASTROMESH_MAIA.md` routing section. Agent placement, least-connections strategy, leader election (bully algorithm). Include routing decision flow.
- `env-vars.md` — Consolidated table of ALL environment variables across the project: Docker entrypoint vars (ASTROMESH_ROLE, ASTROMESH_MESH_ENABLED, etc.), provider keys (OPENAI_API_KEY, ANTHROPIC_API_KEY), WhatsApp vars, ASTROMESH_CONFIG_DIR, ASTROMESH_FORCE_PYTHON, OLLAMA_HOST. Group by category.
- `api-endpoints.md` — Consolidated from `README.md` API reference + `ASTROMESH_OS.md` system endpoints + `ASTROMESH_MAIA.md` mesh endpoints. Every endpoint: method, path, description, request body, response example.
- `cli-commands.md` — Full CLI reference. Every `astromeshctl` and `astromeshd` command with flags, examples, expected output.

**Step 2: Commit**

```bash
git add docs-site/src/content/docs/reference/
git commit -m "feat(docs-site): add Reference section (7 pages)"
```

---

## Task 17: GitHub Actions Docs Workflow

**Files:**
- Create: `.github/workflows/docs.yml`

**Step 1: Create the workflow**

```yaml
name: Deploy Docs

on:
  push:
    branches: [develop]
    paths:
      - 'docs-site/**'
      - 'docs/**'

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build-docs:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: docs-site/package-lock.json

      - name: Install dependencies
        working-directory: docs-site
        run: npm ci

      - name: Build site
        working-directory: docs-site
        run: npm run build

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: docs-site/dist

  deploy-docs:
    needs: build-docs
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

**Step 2: Commit**

```bash
git add .github/workflows/docs.yml
git commit -m "feat(ci): add GitHub Actions workflow for docs site deployment"
```

---

## Task 18: Final Build Verification & Cleanup

**Step 1: Install dependencies and build**

```bash
cd docs-site && npm ci && npm run build
```

Expected: Build succeeds with zero errors. Warnings about unused images or missing optional features are OK.

**Step 2: Preview locally**

```bash
cd docs-site && npm run preview
```

Open `http://localhost:4321/astromech-platform/` and verify:
- Landing page renders all 4 interactive components
- Sidebar navigation shows all sections with correct hierarchy
- Each page loads and renders content
- Internal links between pages work
- Code blocks have syntax highlighting
- Mobile responsive (resize browser)

**Step 3: Remove test page if it exists**

Delete `docs-site/src/content/docs/test.mdx` if it was created during Task 2.

**Step 4: Final commit**

```bash
git add -A docs-site/
git commit -m "feat(docs-site): finalize documentation site build"
```

---

## Execution Notes

- **Tasks 2-5** (interactive components) are independent and can run in parallel.
- **Tasks 7-16** (content pages) are independent and can run in parallel, but each is substantial — dispatching per-section is recommended.
- **Task 6** (landing page) depends on Tasks 2-5 (components must exist to import).
- **Task 17** (CI workflow) is independent of all content tasks.
- **Task 18** depends on all other tasks being complete.

### Content authoring guidance

When writing content pages, follow these principles:
- Start each page with a 1-2 sentence summary of what and why
- Use the "What & Why → Prerequisites → Step-by-step → Verify → Troubleshooting" pattern for deployment guides
- Include expected output after every command
- Use ASCII diagrams from existing docs (they render well in Starlight code blocks)
- Link to related pages within the site, not to the raw `.md` files in `docs/`
- Every YAML snippet should be copy-pasteable and working
- Expand significantly beyond the source `.md` — the source docs are a starting point, not the ceiling
