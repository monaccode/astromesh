# Astromesh Cloud API Reference

**Base URL:** `https://api.astromesh.io/api/v1`

**Content-Type:** `application/json`

**Authentication:** `Authorization: Bearer <jwt_token>` or `X-API-Key: ask-<key>` on all endpoints except auth routes.

---

## Authentication

### POST /auth/google

Exchange a Google ID token for an Astromesh JWT.

> **Status:** Stub in v0.1.0. Returns 501 Not Implemented.

**Request body:**
```json
{ "id_token": "<google_id_token>" }
```

**Response:**
```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 3600,
  "org_slug": "my-org"
}
```

---

### POST /auth/github

Exchange a GitHub OAuth code for an Astromesh JWT.

> **Status:** Stub in v0.1.0. Returns 501 Not Implemented.

**Request body:**
```json
{ "code": "<github_oauth_code>", "state": "<csrf_state>" }
```

**Response:** Same as `/auth/google`.

---

### POST /auth/dev/login

Create or retrieve a dev user and return a JWT. Works now. For development and testing only — do not use in production.

**Request body:**
```json
{
  "email": "dev@example.com",
  "name": "Dev User"
}
```

**Response:**
```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 86400,
  "org_slug": "dev-example-com"
}
```

```bash
curl -X POST https://api.astromesh.io/api/v1/auth/dev/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "name": "Your Name"}'
```

---

### POST /auth/refresh

Refresh an expired JWT using a refresh token.

**Request body:**
```json
{ "refresh_token": "<refresh_token>" }
```

**Response:** New access token with same shape as `/auth/dev/login`.

---

### POST /auth/logout

Invalidate the current token.

**Response:** `204 No Content`

---

## Organizations

### GET /orgs/me

Return the org associated with the authenticated user.

```bash
curl https://api.astromesh.io/api/v1/orgs/me \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "slug": "my-org",
  "display_name": "My Organization",
  "plan": "free",
  "limits": {
    "max_agents": 5,
    "requests_per_day": 1000,
    "max_members": 3
  },
  "created_at": "2026-01-01T00:00:00Z"
}
```

---

### PATCH /orgs/{slug}

Update org display name or settings.

**Path param:** `slug` — org identifier

**Request body** (all fields optional):
```json
{ "display_name": "New Name" }
```

**Response:** Updated org object.

---

### GET /orgs/{slug}/members

List members in the org.

**Response:**
```json
{
  "members": [
    { "email": "owner@example.com", "role": "owner", "joined_at": "2026-01-01T00:00:00Z" },
    { "email": "dev@example.com", "role": "member", "joined_at": "2026-02-01T00:00:00Z" }
  ]
}
```

---

### POST /orgs/{slug}/members/invite

Invite a user to the org by email.

**Request body:**
```json
{ "email": "newmember@example.com", "role": "member" }
```

**Response:** `200 OK` with invitation details. Errors if org is at member limit (3).

---

## Agents

### GET /orgs/{slug}/agents

List all agents in the org.

```bash
curl https://api.astromesh.io/api/v1/orgs/my-org/agents \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "agents": [
    {
      "name": "support-bot",
      "display_name": "Support Bot",
      "status": "deployed",
      "model": "openai/gpt-4o-mini",
      "created_at": "2026-01-15T10:00:00Z",
      "deployed_at": "2026-01-15T10:05:00Z"
    }
  ]
}
```

---

### POST /orgs/{slug}/agents

Create a new agent (draft state).

**Request body** — `WizardConfig` format:
```json
{
  "name": "support-bot",
  "display_name": "Support Bot",
  "step1": {
    "model": "openai/gpt-4o-mini",
    "fallback_model": "ollama/llama3"
  },
  "step2": {
    "system_prompt": "You are a helpful support agent for Acme Corp. Be concise and friendly.",
    "persona": "Support Agent"
  },
  "step3": {
    "tools": ["web_search", "calculator"]
  },
  "step4": {
    "memory_type": "conversational",
    "memory_strategy": "sliding_window",
    "window_size": 20
  },
  "step5": {
    "input_guardrails": ["pii_filter"],
    "output_guardrails": ["content_safety"],
    "max_tokens": 1000
  }
}
```

**Response:** Created agent object with `"status": "draft"`.

```bash
curl -X POST https://api.astromesh.io/api/v1/orgs/my-org/agents \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "support-bot",
    "display_name": "Support Bot",
    "step1": {"model": "openai/gpt-4o-mini"},
    "step2": {"system_prompt": "You are a helpful support agent."}
  }'
```

---

### GET /orgs/{slug}/agents/{name}

Get a single agent's full config and status.

**Path params:** `slug` (org), `name` (agent name)

**Response:** Full agent object including `wizard_config` and current `status`.

---

### PUT /orgs/{slug}/agents/{name}

Update an agent's wizard config. Only allowed when agent is in `draft` or `paused` state. Deployed agents must be paused before editing.

**Request body:** Partial or full `WizardConfig`.

**Response:** Updated agent object.

---

### DELETE /orgs/{slug}/agents/{name}

Delete an agent. Pauses it first if deployed.

**Response:** `204 No Content`

---

### POST /orgs/{slug}/agents/{name}/deploy

Compile the wizard config to Astromesh runtime YAML and register the agent in the shared runtime. Transitions state: `draft` → `deployed` or `paused` → `deployed`.

```bash
curl -X POST https://api.astromesh.io/api/v1/orgs/my-org/agents/support-bot/deploy \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "status": "deployed",
  "agent_id": "my-org__support-bot",
  "deployed_at": "2026-03-17T12:00:00Z"
}
```

---

### POST /orgs/{slug}/agents/{name}/pause

Deregister the agent from the runtime. Transitions state: `deployed` → `paused`. Config is preserved.

**Response:**
```json
{ "status": "paused", "paused_at": "2026-03-17T12:30:00Z" }
```

---

### POST /orgs/{slug}/agents/{name}/test

Run a test query against the agent without incrementing usage counters. Agent must be in `deployed` state.

**Request body:**
```json
{
  "query": "Hello, can you help me?",
  "session_id": "test-session-1"
}
```

**Response:** Same as `/run`.

---

## Execution

### POST /orgs/{slug}/agents/{name}/run

Execute the agent with a query. Agent must be deployed. Supports both JWT and API key auth.

**Request body:**
```json
{
  "query": "What is the refund policy?",
  "session_id": "user-session-abc123",
  "context": {
    "user_id": "usr_456",
    "channel": "web"
  }
}
```

- `query` — Required. The user message.
- `session_id` — Optional. Reuse to maintain conversational memory across calls.
- `context` — Optional. Key-value metadata passed to the agent.

**Response:**
```json
{
  "answer": "Our refund policy allows returns within 30 days of purchase...",
  "session_id": "user-session-abc123",
  "tokens_used": 312,
  "model": "openai/gpt-4o-mini",
  "latency_ms": 1240,
  "trace_id": "trc_789xyz"
}
```

```bash
curl -X POST https://api.astromesh.io/api/v1/orgs/my-org/agents/support-bot/run \
  -H "X-API-Key: ask-your-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the refund policy?",
    "session_id": "sess-001"
  }'
```

---

### WS /orgs/{slug}/agents/{name}/stream

WebSocket endpoint for streaming token-by-token responses.

**Connection:** `wss://api.astromesh.io/api/v1/orgs/{slug}/agents/{name}/stream`

**Auth:** Pass JWT as a query parameter: `?token=<jwt>` (WebSocket headers are not reliably supported by browsers).

**Send message:**
```json
{
  "query": "Explain our pricing",
  "session_id": "sess-001"
}
```

**Receive stream events:**
```json
{ "type": "token", "content": "Our" }
{ "type": "token", "content": " pricing" }
{ "type": "token", "content": " starts" }
{ "type": "done", "answer": "Our pricing starts at...", "tokens_used": 89 }
```

---

## API Keys

### GET /orgs/{slug}/keys

List all API keys for the org (secrets are masked).

**Response:**
```json
{
  "keys": [
    {
      "id": "key_abc123",
      "name": "Production",
      "prefix": "ask-prod",
      "created_at": "2026-01-01T00:00:00Z",
      "last_used_at": "2026-03-16T08:00:00Z"
    }
  ]
}
```

---

### POST /orgs/{slug}/keys

Create a new API key. The full secret is returned **once** — store it securely.

**Request body:**
```json
{ "name": "Production" }
```

**Response:**
```json
{
  "id": "key_abc123",
  "name": "Production",
  "secret": "ask-prod-xxxxxxxxxxxxxxxxxxxxxxxx",
  "created_at": "2026-03-17T12:00:00Z"
}
```

---

### DELETE /orgs/{slug}/keys/{key_id}

Revoke and delete an API key. Immediately stops accepting requests with that key.

**Response:** `204 No Content`

---

## Provider Keys (BYOK)

Store your LLM provider API keys in Astromesh Cloud. They are encrypted at rest and injected into the runtime at execution time.

### GET /orgs/{slug}/providers

List configured provider keys (secrets masked).

**Response:**
```json
{
  "providers": [
    { "provider": "openai", "masked_key": "sk-...xxxx", "added_at": "2026-01-01T00:00:00Z" },
    { "provider": "anthropic", "masked_key": "sk-ant-...xxxx", "added_at": "2026-02-01T00:00:00Z" }
  ]
}
```

---

### POST /orgs/{slug}/providers

Add or update a provider key.

**Request body:**
```json
{
  "provider": "openai",
  "api_key": "sk-your-openai-key-here"
}
```

**Supported providers:** `openai`, `anthropic`, `groq`, `mistral`, `cohere`, `ollama`

**Response:** `200 OK` — `{ "provider": "openai", "status": "saved" }`

```bash
curl -X POST https://api.astromesh.io/api/v1/orgs/my-org/providers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": "openai", "api_key": "sk-..."}'
```

---

### DELETE /orgs/{slug}/providers/{provider}

Remove a provider key.

**Response:** `204 No Content`

---

## Usage

### GET /orgs/{slug}/usage

Get request counts and token usage for the org.

**Query params:**
- `days` — Number of days to look back (default: 30, max: 90)

```bash
curl "https://api.astromesh.io/api/v1/orgs/my-org/usage?days=7" \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "period_days": 7,
  "total_requests": 423,
  "total_tokens": 189540,
  "daily_limit": 1000,
  "remaining_today": 577,
  "by_agent": [
    { "agent": "support-bot", "requests": 310, "tokens": 142000 },
    { "agent": "faq-bot", "requests": 113, "tokens": 47540 }
  ],
  "by_day": [
    { "date": "2026-03-17", "requests": 68, "tokens": 29800 }
  ]
}
```

---

## Agent Lifecycle State Machine

```
         POST /agents
              │
              ▼
          [draft]
              │
    POST .../deploy
              │
              ▼
         [deployed] ◄────────────────┐
              │                      │
   POST .../pause           POST .../deploy
              │                      │
              ▼                      │
          [paused] ──────────────────┘
```

| Transition | Endpoint | Effect |
|---|---|---|
| draft → deployed | POST .../deploy | Compiles YAML, registers in runtime |
| deployed → paused | POST .../pause | Deregisters from runtime |
| paused → deployed | POST .../deploy | Re-registers in runtime |
| any → deleted | DELETE /agents/{name} | Pauses then removes |

---

## Rate Limits

| Resource | Limit |
|---|---|
| Agents per org | 5 |
| Requests per day | 1,000 |
| Members per org | 3 |
| Streaming connections | 5 concurrent |

Rate limit headers are included on execution endpoints:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 577
X-RateLimit-Reset: 1742256000
```

---

## Error Format

All errors return a consistent JSON envelope:

```json
{
  "error": "agent_not_deployed",
  "message": "Agent 'support-bot' is in draft state. Deploy it first.",
  "status": 400
}
```

Common error codes:
- `401 Unauthorized` — Missing or invalid token/key
- `403 Forbidden` — Valid auth but wrong org
- `404 Not Found` — Agent or resource doesn't exist
- `409 Conflict` — Agent already in target state
- `429 Too Many Requests` — Daily limit reached
- `501 Not Implemented` — Feature is a stub (Google/GitHub OAuth in v0.1.0)
