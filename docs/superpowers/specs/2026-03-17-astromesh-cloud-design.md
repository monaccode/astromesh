# Astromesh Cloud — Design Spec v1

## Goal

Build **Astromesh Cloud**, a managed platform where PYMEs can visually design, configure, and deploy AI agents without infrastructure setup. The platform leverages the existing Astromesh runtime and ADK, adding a multi-tenant layer (auth, organizations, agent CRUD) and a no-code Agent Studio (step-by-step wizard).

## Target User

Small and medium businesses (PYMEs) starting with AI agents. Non-technical or semi-technical users who want to go from "idea" to "running agent with API endpoint" without writing code or managing infrastructure.

## Architecture

Three independent services communicating via HTTP:

```
┌───────────────────────────────────────────────────────────┐
│                     Astromesh Cloud                        │
│                                                           │
│  ┌────────────┐    ┌───────────────┐    ┌──────────────┐ │
│  │  Next.js   │───▶│   Cloud API   │───▶│  Astromesh    │ │
│  │  Studio    │    │   (FastAPI)   │    │   Runtime    │ │
│  │  (Web App) │◀───│  Auth / Orgs  │◀───│  (existing)  │ │
│  └────────────┘    └───────────────┘    └──────────────┘ │
│                           │                               │
│                    ┌──────┴──────┐                        │
│                    │  PostgreSQL  │                        │
│                    │  (Cloud DB)  │                        │
│                    └─────────────┘                        │
└───────────────────────────────────────────────────────────┘
```

- **Next.js Studio** — Web app. Login, wizard, agent management, usage dashboard.
- **Cloud API** — New FastAPI service. Auth (Google/GitHub OAuth), organizations, agent CRUD, proxy execution to runtime. Own PostgreSQL database for users, orgs, agents, API keys.
- **Astromesh Runtime** — The existing runtime, unmodified. Cloud API sends requests as any HTTP client. Logical isolation per org via naming conventions.

**Key principle:** The runtime does not know it is "cloud". Cloud API is an orchestrator that translates "org X wants to run agent Y" into a runtime call with the correct namespace.

---

## Data Model

### User

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `email` | string | unique |
| `name` | string | display name |
| `avatar_url` | string | nullable |
| `auth_provider` | enum | google / github |
| `auth_provider_id` | string | provider's user ID |

**Account collision:** If a user signs up with Google and later tries GitHub with the same email, the auth flow surfaces: "An account already exists with this email via Google. Please sign in with Google." Email-based account merging is deferred to v2.
| `created_at` | timestamp | |
| `last_login_at` | timestamp | |

### Organization

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `slug` | string | unique, URL-friendly |
| `name` | string | display name |
| `created_at` | timestamp | |

Auto-created on first user login. The creating user becomes `owner`.

### OrgMember

| Field | Type | Notes |
|-------|------|-------|
| `user_id` | UUID | FK → User, composite PK |
| `org_id` | UUID | FK → Organization, composite PK |
| `role` | enum | owner / admin / member |

Composite primary key `(user_id, org_id)` prevents duplicate memberships. A user can belong to multiple orgs.

### Agent

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `org_id` | UUID | FK → Organization |
| `name` | string | slug, unique per org |
| `display_name` | string | |
| `config` | JSONB | full agent config (model, tools, memory, guardrails, orchestration) |
| `status` | enum | draft / deployed / paused |
| `runtime_name` | string | `{org_slug}--{agent_name}` |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |
| `deployed_at` | timestamp | nullable |

### ApiKey

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `org_id` | UUID | FK → Organization |
| `key_hash` | string | bcrypt hash |
| `prefix` | string | first 8 chars, displayed as `am_XXXXXXXX...` |
| `name` | string | user-given label |
| `scopes` | array | `agent:run`, `agent:manage`, etc. |
| `created_at` | timestamp | |
| `expires_at` | timestamp | nullable |

### ProviderKey

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `org_id` | UUID | FK → Organization |
| `provider` | string | openai / anthropic / etc. |
| `encrypted_key` | bytes | Fernet-encrypted at rest |
| `created_at` | timestamp | |

### UsageLog

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `org_id` | UUID | FK → Organization |
| `agent_id` | UUID | FK → Agent |
| `tokens_in` | int | |
| `tokens_out` | int | |
| `model` | string | |
| `cost_usd` | decimal | estimated |
| `created_at` | timestamp | |

---

## Authentication

- **Google OAuth** — Primary. PYMEs commonly use Google Workspace.
- **GitHub OAuth** — Secondary. For technical users connecting with ADK.
- **Flow:** OAuth callback → Cloud API verifies token with provider → creates or updates User → auto-creates Organization if first login → returns JWT (access + refresh tokens).
- **JWT:** Short-lived access token (15 min) + long-lived refresh token (7 days). Stored in httpOnly cookies.
- **NextAuth.js** on the frontend handles the OAuth dance and token refresh.

---

## Multi-tenant Isolation

The existing runtime is not modified. Cloud API implements isolation via naming conventions:

### Agent names
- Format: `{org_slug}--{agent_name}`
- Org "acme" creates agent "soporte" → runtime receives `acme--soporte`
- Cloud API always prepends the org_slug; the user never sees the prefix.

### Session IDs
- Format: `{org_slug}:{session_id}`
- Conversational memory is automatically isolated per org.
- **Important:** The Cloud API's `runtime_proxy.py` is responsible for always rewriting `session_id` to `{org_slug}:{user_session_id}` before forwarding to the runtime. The runtime receives the prefixed ID transparently.

### Runtime agent config
- Cloud API translates the wizard config into valid Astromesh agent YAML.
- Injects it to the runtime via `POST /v1/agents` (needs implementation — already listed in `docs/ADK_PENDING.md`).
- Removal via `DELETE /v1/agents/{name}`.

### Agent persistence on runtime restart
- The runtime stores agents in-memory (`_agents` dict) — dynamically registered agents are lost on restart.
- **Solution:** Cloud API runs a **reconciliation loop** on startup: queries all agents with `status=deployed` from Cloud DB and re-registers each one via `POST /v1/agents` on the runtime.
- Cloud API also exposes a `GET /health` that checks runtime connectivity and triggers reconciliation if agents are missing.

### Provider keys (BYOK)
- When an agent uses BYOK, Cloud API decrypts the key and injects it into the runtime request via the `X-Astromesh-Provider-Key` header along with `X-Astromesh-Provider-Name` (e.g., `openai`).
- **Runtime change required:** The `POST /v1/agents/{name}/run` endpoint reads these headers and passes them to `ModelRouter` as request-scoped overrides. The key is used for that single execution and never persisted. If the headers are absent, the runtime uses its own configured provider keys as today.
- The Cloud API validates that the agent's configured model provider matches the available key before proxying.

### Org limits (v1, hardcoded)

| Limit | Enforcement point |
|-------|-------------------|
| Max 5 deployed agents per org | `POST /orgs/{slug}/agents/{name}/deploy` — checks count before calling runtime |
| Max 1,000 requests/day per org | `POST /orgs/{slug}/agents/{name}/run` and `/stream` — queries `UsageLog` count for current day (acceptable DB hit for v1; Redis cache in v2) |
| Max 3 members per org | `POST /orgs/{slug}/members/invite` — checks count before creating invite |
| Open source models | No token limit applied |

---

## Agent Studio — Wizard

5-step wizard with live preview panel on the right side.

### Step 1 — Identity
- Agent name (auto-generated slug)
- System prompt textarea with placeholder guide: "You are an assistant that..."
- Tone/personality visual selector: Professional, Casual, Technical, Empathetic. Each maps to a prefix sentence injected into the system prompt by `config_builder.py` (e.g., Professional → "Respond in a professional, clear tone.", Casual → "Respond in a friendly, conversational tone.")

### Step 2 — Model
- Curated card list:
  - **Included** (badge "Free"): Llama 3, Mistral, Phi-3 (via Ollama on shared cluster)
  - **BYOK** (badge "Bring your key"): GPT-4o, Claude Sonnet, Gemini
- If BYOK selected and no key configured → inline modal to add it
- Routing strategy in simple language: "Cheapest", "Fastest", "Best quality"

### Step 3 — Tools
- Visual catalog with toggle on/off per tool
- Each tool shows: icon, name, short description
- Inline configuration if the tool requires it (e.g., webhook URL, SMTP settings)

### Step 4 — Settings
- **Memory:** toggle "Remember conversations" → activates conversational memory (namespaced per org)
- **Guardrails:** toggles in simple language:
  - "Filter personal information (PII)" on/off
  - "Inappropriate content filter" on/off
- **Orchestration:** selector with explanations:
  - "Respond directly" → single pass
  - "Think step by step" → ReAct
  - "Plan before acting" → PlanAndExecute

### Step 5 — Preview & Deploy
- Generated YAML preview (collapsible, for technical users)
- "Test Agent" button → inline chat to test before deploy
- "Deploy" button → creates the agent on the runtime
- Post-deploy: shows API endpoint + code snippets (curl, Python with ADK, JavaScript)

---

## Tool Catalog

### Available in v1

| Tool | Category | Description |
|------|----------|-------------|
| `web_search` | Search | Real-time web search |
| `calculator` | Utility | Math operations |
| `datetime` | Utility | Date, time, timezones |
| `json_parser` | Utility | Parse and transform JSON |
| `http_request` | Integration | Call external APIs (GET/POST) |
| `email_sender` | Communication | Send emails via SMTP |
| `file_reader` | Data | Read files (PDF, CSV, TXT) |
| `text_summarizer` | AI | Summarize long texts |
| `translator` | AI | Translate between languages |
| `code_executor` | Dev | Execute Python snippets (sandboxed) |

### Coming Soon (visible but disabled, with "Notify me" button)

| Tool | Category | Why important |
|------|----------|---------------|
| `google_sheets` | Integration | PYMEs live in Google Sheets |
| `google_calendar` | Integration | Agents that schedule meetings |
| `google_drive` | Integration | Internal document access |
| `slack_bot` | Communication | Primary channel for many PYMEs |
| `whatsapp` | Communication | Already exists in Astromesh, needs config UI |
| `notion` | Productivity | Enterprise knowledge bases |
| `hubspot_crm` | Sales | Popular CRM for PYMEs |
| `stripe` | Payments | Query payments, invoices |
| `sql_query` | Data | Query customer databases |
| `rag_pipeline` | AI | Upload documents and search within them |
| `image_generator` | AI | Generate images (DALL-E, SD) |
| `voice_transcriber` | AI | Audio to text (Whisper) |

"Coming Soon" tools are shown with attenuated design. The "Notify me" button measures interest for prioritization.

---

## Cloud API — Endpoints

All endpoints prefixed with `/api/v1`.

### Auth
- `POST /auth/google` — OAuth callback, creates user + org if new, returns JWT
- `POST /auth/github` — same with GitHub
- `POST /auth/refresh` — renew JWT
- `POST /auth/logout` — invalidate token

### Organizations
- `GET /orgs/me` — current user's org
- `PATCH /orgs/{slug}` — update name/settings
- `GET /orgs/{slug}/members` — list members
- `POST /orgs/{slug}/members/invite` — invite by email
- `DELETE /orgs/{slug}/members/{user_id}` — remove member

### Agents
- `GET /orgs/{slug}/agents` — list agents (with status)
- `POST /orgs/{slug}/agents` — create agent (wizard config), sets `status=draft`, does NOT touch runtime
- `GET /orgs/{slug}/agents/{name}` — agent detail
- `PUT /orgs/{slug}/agents/{name}` — update config. If agent is `deployed`, transitions to `draft` and removes from runtime (requires re-deploy)
- `DELETE /orgs/{slug}/agents/{name}` — delete (removes from runtime if deployed)
- `POST /orgs/{slug}/agents/{name}/deploy` — validates config, calls runtime `POST /v1/agents`, sets `status=deployed` + `deployed_at`
- `POST /orgs/{slug}/agents/{name}/pause` — calls runtime `DELETE /v1/agents/{name}`, sets `status=paused`
- `POST /orgs/{slug}/agents/{name}/test` — execute in test mode using a disposable session ID (`__test__:{uuid}`). After execution, Cloud API deletes the test session memory via runtime `DELETE /v1/memory/{agent}/history/{session_id}`

### Execution (proxy to runtime)
- `POST /orgs/{slug}/agents/{name}/run` — execute agent (proxies to runtime `/v1/agents/{runtime_name}/run`)
- `WS /orgs/{slug}/agents/{name}/stream` — streaming via WebSocket

### API Keys
- `GET /orgs/{slug}/keys` — list keys (prefix only visible)
- `POST /orgs/{slug}/keys` — create key (returns full key once)
- `DELETE /orgs/{slug}/keys/{id}` — revoke

### Provider Keys
- `GET /orgs/{slug}/providers` — list configured providers (keys hidden)
- `POST /orgs/{slug}/providers` — save encrypted key
- `DELETE /orgs/{slug}/providers/{provider}` — delete

### Usage
- `GET /orgs/{slug}/usage` — usage summary (tokens, requests, estimated cost) filterable by period

---

## Tech Stack

### Frontend
- Next.js 14+ with App Router
- Tailwind CSS + Astromesh brand palette (cyan `#00d4ff`, dark surfaces `#0a0e14`)
- NextAuth.js for Google/GitHub OAuth
- Zustand for state management
- React Hook Form for wizard
- Location: `astromesh-cloud/web/`

### Cloud API
- FastAPI + Pydantic v2
- SQLAlchemy async + asyncpg (PostgreSQL)
- python-jose for JWT
- cryptography (Fernet) for provider key encryption
- httpx for runtime proxy
- Alembic for migrations
- Location: `astromesh-cloud/api/`

### Infrastructure (v1)
- PostgreSQL (Cloud DB)
- Astromesh Runtime (existing, unmodified except 2 CRUD endpoints)
- Docker Compose for local development
- Single server deployment: Cloud API + Runtime + PostgreSQL + Ollama

---

## Runtime Prerequisites

Changes needed in the existing Astromesh runtime:

### New endpoints (already listed in `docs/ADK_PENDING.md`)
- `POST /v1/agents` — Register a new agent dynamically (accepts agent config as JSON, adds to in-memory `_agents` dict)
- `DELETE /v1/agents/{name}` — Remove a dynamically registered agent from `_agents`

### Modifications to existing endpoints
- **`POST /v1/agents/{name}/run`** — Read optional `X-Astromesh-Provider-Key` and `X-Astromesh-Provider-Name` headers. If present, pass to `ModelRouter` as request-scoped provider key override.
- **`POST /v1/agents/{name}/run` response** — Add `usage` field to `AgentRunResponse`: `{ "tokens_in": int, "tokens_out": int, "model": str }`. Extracted from the trace's `response.usage` data that is already tracked internally.

These are minimal, backward-compatible changes — the headers and usage field are optional.

---

## Project Structure

```
astromesh-cloud/
├── web/                          # Next.js Studio
│   ├── src/
│   │   ├── app/                  # App Router pages
│   │   │   ├── (auth)/           # Login, callback pages
│   │   │   ├── (dashboard)/      # Main app layout
│   │   │   │   ├── agents/       # Agent list, detail
│   │   │   │   ├── studio/       # Wizard (create/edit)
│   │   │   │   ├── settings/     # Org, API keys, providers
│   │   │   │   └── usage/        # Usage dashboard
│   │   │   └── layout.tsx
│   │   ├── components/
│   │   │   ├── wizard/           # Wizard steps
│   │   │   ├── agent/            # Agent cards, detail
│   │   │   ├── chat/             # Test chat panel
│   │   │   └── ui/               # Shared UI primitives
│   │   ├── lib/                  # API client, auth, utils
│   │   └── styles/               # Tailwind config, globals
│   ├── package.json
│   ├── tailwind.config.ts
│   └── next.config.ts
├── api/                          # Cloud API (FastAPI)
│   ├── astromesh_cloud/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI app, CORS, middleware
│   │   ├── config.py             # Settings (env vars)
│   │   ├── database.py           # SQLAlchemy async engine
│   │   ├── models/               # SQLAlchemy models
│   │   │   ├── user.py
│   │   │   ├── organization.py
│   │   │   ├── agent.py
│   │   │   ├── api_key.py
│   │   │   ├── provider_key.py
│   │   │   └── usage_log.py
│   │   ├── schemas/              # Pydantic request/response
│   │   │   ├── auth.py
│   │   │   ├── agent.py
│   │   │   ├── organization.py
│   │   │   └── usage.py
│   │   ├── routes/               # API route modules
│   │   │   ├── auth.py
│   │   │   ├── agents.py
│   │   │   ├── organizations.py
│   │   │   ├── keys.py
│   │   │   ├── providers.py
│   │   │   ├── execution.py
│   │   │   └── usage.py
│   │   ├── services/             # Business logic
│   │   │   ├── auth_service.py
│   │   │   ├── agent_service.py
│   │   │   ├── runtime_proxy.py  # HTTP client to Astromesh runtime
│   │   │   ├── config_builder.py # Wizard config → YAML translation
│   │   │   └── encryption.py     # Fernet key encryption
│   │   └── middleware/           # Auth middleware, rate limiting
│   │       ├── auth.py
│   │       └── rate_limit.py
│   ├── alembic/                  # DB migrations
│   ├── pyproject.toml
│   └── Dockerfile
├── docker-compose.yaml           # Local dev: web + api + postgres + runtime + ollama
└── README.md
```

---

## v2 Roadmap (Pending)

Items explicitly deferred from v1:

### Infrastructure
- Redis for rate limiting and session caching
- S3/MinIO for file storage (file_reader tool)
- Kubernetes deployment for production scaling
- CI/CD pipeline (GitHub Actions)
- Vercel/Cloudflare CDN for frontend
- Sentry for error tracking

### Product
- **Canvas visual builder** — Node-based drag-and-drop (evolution of wizard)
- **Billing & plans** — Stripe integration, usage-based pricing, plan tiers
- **Dedicated runtime per org** — Premium plan with isolated containers
- **All "Coming Soon" tools** — Google Sheets, Calendar, Drive, Slack, WhatsApp config UI, Notion, HubSpot, Stripe, SQL, RAG pipeline, image gen, voice transcription
- **Advanced monitoring dashboard** — Real-time traces, metrics, cost analytics
- **Multi-agent teams in wizard** — Visual composition of agent teams (supervisor, swarm, pipeline, parallel)

### Security & Governance
- Granular roles (viewer, editor, admin, owner)
- Audit log of actions per org
- Custom domains for API endpoints
- SOC 2 compliance preparation

### Developer Experience
- Webhook notifications on agent execution events
- JavaScript SDK for embedding agents in web apps
- Agent versioning and rollback
- Agent templates marketplace
- Import/export agent configs
- ADK CLI integration with Cloud (`astromesh-adk deploy --cloud`)
