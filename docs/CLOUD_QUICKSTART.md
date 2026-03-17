# Astromesh Cloud — Quick Start

Get from zero to a running AI agent in under 10 minutes.

**Prerequisites:** `curl` and a terminal.

---

## Step 1: Log In

Use the dev login endpoint (Google/GitHub OAuth coming soon):

```bash
TOKEN=$(curl -s -X POST https://api.astromesh.io/api/v1/auth/dev/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "name": "Your Name"}' \
  | jq -r '.access_token')

echo "Logged in. Token: ${TOKEN:0:20}..."
```

Get your org slug:

```bash
ORG=$(curl -s https://api.astromesh.io/api/v1/orgs/me \
  -H "Authorization: Bearer $TOKEN" \
  | jq -r '.slug')

echo "Org: $ORG"
```

---

## Step 2: Add Your Provider Key (BYOK)

Store your OpenAI (or other provider) key so agents can call the model:

```bash
curl -X POST "https://api.astromesh.io/api/v1/orgs/$ORG/providers" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": "openai", "api_key": "sk-your-openai-key-here"}'
```

No provider key? Use `ollama/llama3` in Step 3 — it runs on the shared Ollama instance included in the platform.

---

## Step 3: Create an Agent

Create a support bot in draft state:

```bash
curl -X POST "https://api.astromesh.io/api/v1/orgs/$ORG/agents" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-first-agent",
    "display_name": "My First Agent",
    "step1": {
      "model": "openai/gpt-4o-mini"
    },
    "step2": {
      "system_prompt": "You are a helpful assistant. Answer questions clearly and concisely.",
      "persona": "Assistant"
    },
    "step3": {
      "tools": []
    },
    "step4": {
      "memory_type": "conversational",
      "memory_strategy": "sliding_window",
      "window_size": 10
    },
    "step5": {}
  }'
```

You should see `"status": "draft"` in the response.

---

## Step 4: Deploy It

Compile the config and register the agent in the runtime:

```bash
curl -X POST "https://api.astromesh.io/api/v1/orgs/$ORG/agents/my-first-agent/deploy" \
  -H "Authorization: Bearer $TOKEN"
```

Response:
```json
{
  "status": "deployed",
  "agent_id": "my-org__my-first-agent",
  "deployed_at": "2026-03-17T12:00:00Z"
}
```

---

## Step 5: Run It

Send a query to your deployed agent:

```bash
curl -X POST "https://api.astromesh.io/api/v1/orgs/$ORG/agents/my-first-agent/run" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "Hello! What can you help me with?", "session_id": "sess-001"}'
```

Response:
```json
{
  "answer": "I can help you with a wide range of questions...",
  "session_id": "sess-001",
  "tokens_used": 87,
  "model": "openai/gpt-4o-mini",
  "latency_ms": 950
}
```

---

## Step 6: Get an API Key for Production Use

JWT tokens expire. For production integrations, create a long-lived API key:

```bash
SECRET=$(curl -s -X POST "https://api.astromesh.io/api/v1/orgs/$ORG/keys" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Production"}' \
  | jq -r '.secret')

echo "API Key: $SECRET"
# Store this securely — it won't be shown again
```

Use the API key in production calls:

```bash
curl -X POST "https://api.astromesh.io/api/v1/orgs/$ORG/agents/my-first-agent/run" \
  -H "X-API-Key: $SECRET" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the weather like?", "session_id": "prod-sess-123"}'
```

---

## Full Example: Login → Create → Deploy → Run

A single script that does everything above end to end:

```bash
#!/usr/bin/env bash
set -e

BASE="https://api.astromesh.io/api/v1"
EMAIL="you@example.com"

# 1. Login
echo "→ Logging in..."
AUTH=$(curl -s -X POST "$BASE/auth/dev/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$EMAIL\", \"name\": \"Dev\"}")
TOKEN=$(echo $AUTH | jq -r '.access_token')
ORG=$(curl -s "$BASE/orgs/me" -H "Authorization: Bearer $TOKEN" | jq -r '.slug')
echo "  Org: $ORG"

# 2. Create agent
echo "→ Creating agent..."
curl -s -X POST "$BASE/orgs/$ORG/agents" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "quickstart-bot",
    "display_name": "Quickstart Bot",
    "step1": {"model": "ollama/llama3"},
    "step2": {"system_prompt": "You are a helpful assistant."}
  }' | jq '.status'

# 3. Deploy
echo "→ Deploying..."
curl -s -X POST "$BASE/orgs/$ORG/agents/quickstart-bot/deploy" \
  -H "Authorization: Bearer $TOKEN" | jq '.status'

# 4. Run
echo "→ Running query..."
curl -s -X POST "$BASE/orgs/$ORG/agents/quickstart-bot/run" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "Say hello!", "session_id": "qs-001"}' | jq '.answer'

echo "Done!"
```

---

## Using with ADK

Connect your ADK agents to Astromesh Cloud for remote execution:

```python
from astromesh_adk import agent, connect

# Define your agent locally
@agent(name="my-first-agent", model="openai/gpt-4o-mini")
async def my_agent(ctx):
    """You are a helpful assistant."""
    return None

# Connect to Cloud — routes execution to your deployed agent
connect(
    url="https://api.astromesh.io",
    api_key="ask-your-key-here",
    org="your-org-slug"
)

# Same interface, executes remotely
result = await my_agent.run("Hello from ADK!")
print(result.answer)
```

Or use the context manager for scoped remote execution:

```python
from astromesh_adk import remote

async with remote("https://api.astromesh.io", api_key="ask-...", org="my-org"):
    result = await my_agent.run("Remote query")

# Back to local after the context block
result = await my_agent.run("Local query")
```

---

## What's Next

- **Studio** — Visit `studio.astromesh.io` to build agents visually with the 5-step wizard
- **Add tools** — See `CLOUD_API_REFERENCE.md` for the available tool catalog
- **Monitor usage** — `GET /orgs/{slug}/usage` for request counts and token totals
- **Streaming** — Use the WebSocket endpoint at `.../stream` for real-time responses
- **Invite teammates** — `POST /orgs/{slug}/members/invite` to add up to 3 members
