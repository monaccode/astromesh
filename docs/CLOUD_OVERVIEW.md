# Astromesh Cloud — Developer Overview

Astromesh Cloud is a managed platform for deploying AI agents without managing infrastructure. It builds on the open-source Astromesh runtime and ADK, wrapping them in a multi-tenant SaaS layer with a visual Studio, a Cloud API, and shared execution infrastructure.

**Target audience:** Small and medium teams (PYMEs) that want production-ready AI agents in hours, not weeks.

---

## Architecture

Three services compose the platform:

```
┌─────────────────────────┐
│   Studio (Next.js)      │  Visual agent builder — 5-step wizard, drag-and-drop tools
│   studio.astromesh.io   │  Connects to Cloud API via JWT
└─────────────┬───────────┘
              │ REST / WebSocket
┌─────────────▼───────────┐
│   Cloud API (FastAPI)   │  /api/v1 — Auth, orgs, agents, keys, usage
│   api.astromesh.io      │  Manages agent configs, lifecycle, BYOK provider keys
└─────────────┬───────────┘
              │ AgentRuntime.run()
┌─────────────▼───────────┐
│  Astromesh Runtime      │  Same open-source engine (AgentRuntime + ModelRouter + ToolRegistry)
│  (shared, multi-tenant) │  Agents isolated by org naming convention: {org_slug}__{agent_name}
└─────────────────────────┘
```

The runtime is the same engine described in the core Astromesh docs — the Cloud layer adds auth, multi-tenancy, the visual Studio, and the managed ops around it.

---

## Multi-tenancy

Tenant isolation is implemented via **naming conventions**, not separate processes:

- Every agent registered in the runtime is prefixed: `{org_slug}__{agent_name}`
- Every API key belongs to a single org and can only invoke agents in that org
- Provider keys (BYOK) are stored encrypted and injected at execution time

There are no hard container boundaries between tenants in v0.1.0. Full workload isolation is on the roadmap.

---

## How It Works

1. **Design** — Use Studio's 5-step wizard to configure your agent: name/model, system prompt, tools, memory, and guardrails
2. **Draft** — Agent config is saved as a `WizardConfig` JSON document attached to your org
3. **Deploy** — POST to `/deploy` → Cloud API converts the wizard config to an Astromesh YAML, registers it in the shared runtime
4. **Execute** — POST to `/run` → Cloud API validates your JWT or API key, routes the query to `runtime.run(agent_id, query, session_id)`
5. **Stream** — WebSocket at `/stream` for token-by-token streaming responses

---

## Authentication

Two authentication methods:

| Method | Use case |
|---|---|
| **JWT (Bearer token)** | Interactive use — Studio, direct API calls, testing |
| **API Key (`ask-` prefix)** | Production integrations — server-to-server, CI/CD |

JWT tokens are obtained via OAuth or the dev login endpoint. API keys are created per-org and scoped to that org's agents.

### OAuth Providers

- **Google** — `/auth/google` (stub in v0.1.0, full OIDC flow coming)
- **GitHub** — `/auth/github` (stub in v0.1.0, full OAuth flow coming)
- **Dev login** — `/auth/dev/login` — works now, for development and testing only

---

## Key Concepts

### Organizations

An org is the top-level tenant. Every resource (agents, API keys, provider keys, members) belongs to an org. Orgs have a `slug` (URL-safe name used in all API paths) and a `display_name`.

Limits per org (v0.1.0):
- 5 agents
- 1,000 requests per day
- 3 members

### Agents

Agents have a **lifecycle** with three states:

```
draft ──────→ deployed ──────→ paused
  ↑               │               │
  └───────────────┴───────────────┘
         (re-deploy / unpause)
```

- **draft** — Config saved, not running. Can be edited freely.
- **deployed** — Config compiled to runtime YAML, registered in AgentRuntime. Accepting requests.
- **paused** — Deregistered from runtime. Config preserved. No requests accepted.

### API Keys

API keys (`ask-` prefix) are the recommended way to call agents from production code. They are scoped to an org, never expire by default, and can be revoked individually.

### Provider Keys (BYOK)

Bring Your Own Key — store your OpenAI, Anthropic, Groq, or other provider API keys in Astromesh Cloud. They are encrypted at rest and injected into the runtime's ModelRouter at agent execution time. This means you pay providers directly; Astromesh Cloud only charges for the platform.

---

## Versioning

Current version: **v0.1.0**

Some features are stubs or in active development:
- Google/GitHub OAuth are registered routes but not fully implemented
- Studio is the primary interface; full API-only workflows work via dev login + API keys
- Workload isolation between tenants is naming-convention-based (not containerized)
