---
title: WhatsApp Integration
description: Receive and reply to WhatsApp messages through your agents
---

Astromesh includes a WhatsApp channel adapter that connects any configured agent to WhatsApp via Meta's Business Cloud API. Messages arrive as webhooks, flow through the standard agent execution pipeline (memory, LLM, tools, guardrails), and responses are sent back to the user automatically.

## Overview

```
WhatsApp User
    |
    v
Meta Cloud API --webhook--> POST /v1/channels/whatsapp/webhook
                                |
                                v
                          WhatsAppClient.parse_webhook()
                                |
                                v
                          AgentRuntime.run(
                              agent_name=config.default_agent,
                              query=message_text,
                              session_id=phone_number
                          )
                                |
                                v
                          WhatsAppClient.send_message(phone, response)
                                |
                                v
                          POST graph.facebook.com/v21.0/{phone_id}/messages
                                |
                                v
                          WhatsApp User receives response
```

The adapter does not modify the runtime, memory, orchestration, or guardrails layers. It is a thin translation layer between Meta's webhook format and Astromesh's `runtime.run()` interface.

## Prerequisites

Before setting up the integration, you need:

- A [Meta Business account](https://business.facebook.com/)
- Access to the [WhatsApp Business API](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started) (apply through Meta Developer portal)
- A public HTTPS URL reachable from Meta's servers (for the webhook endpoint)
- An Astromesh instance running with at least one agent configured

## Setup

### Step 1: Create a Meta App

1. Go to [developers.facebook.com](https://developers.facebook.com/) and create a new app
2. Select "Business" as the app type
3. In the app dashboard, click "Add Product" and enable **WhatsApp**
4. Follow Meta's onboarding flow to get a test phone number

### Step 2: Get Your Credentials

From the Meta App Dashboard, navigate to WhatsApp > API Setup and note the following:

- **Temporary Access Token** (or generate a permanent System User token for production)
- **Phone Number ID** (displayed under the test number)
- **App Secret** (found in Settings > Basic)

Choose a **Verify Token** — this is an arbitrary string you create. You will configure it both in Astromesh and in the Meta dashboard.

### Step 3: Configure Environment Variables

Set the following environment variables on the machine or container running Astromesh:

| Variable | Description | Example |
|----------|-------------|---------|
| `WHATSAPP_VERIFY_TOKEN` | Arbitrary string for webhook verification | `my-secret-verify-token-2026` |
| `WHATSAPP_ACCESS_TOKEN` | Meta API access token | `EAABx...` |
| `WHATSAPP_PHONE_NUMBER_ID` | Business phone number ID | `106543218765432` |
| `WHATSAPP_APP_SECRET` | App secret for signature validation | `a1b2c3d4e5f6...` |

The `WHATSAPP_APP_SECRET` is optional but strongly recommended. Without it, webhook signature validation is skipped, and any HTTP client could send fake messages to your endpoint.

### Step 4: Create Channel Configuration

Create or update `config/channels.yaml`:

```yaml
channels:
  whatsapp:
    verify_token: "${WHATSAPP_VERIFY_TOKEN}"
    access_token: "${WHATSAPP_ACCESS_TOKEN}"
    phone_number_id: "${WHATSAPP_PHONE_NUMBER_ID}"
    app_secret: "${WHATSAPP_APP_SECRET}"
    default_agent: "whatsapp-assistant"
```

The `default_agent` field specifies which agent handles incoming WhatsApp messages. This must match an agent defined in `config/agents/`.

### Step 5: Create the Agent

Create `config/agents/whatsapp-assistant.agent.yaml`:

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: whatsapp-assistant
spec:
  identity:
    role: "Helpful assistant"
    personality: "Friendly, concise, and practical"
  model:
    primary:
      provider: openai
      model: gpt-4o-mini
    routing:
      strategy: cost_optimized
  prompts:
    system: |
      You are a helpful assistant communicating via WhatsApp.
      Keep responses short and conversational — users are on mobile.
      Use plain text only (no markdown formatting).
  orchestration:
    pattern: react
    max_iterations: 5
    timeout: 25
  memory:
    conversational:
      backend: redis
      strategy: sliding_window
      max_messages: 20
  guardrails:
    input:
      - type: pii_redaction
    output:
      - type: pii_redaction
```

Key considerations for WhatsApp agents:

- Keep responses concise (WhatsApp UX favors short messages)
- Set a timeout under 25 seconds to stay within Meta's expectations
- Use `session_id=phone_number` — the adapter sets this automatically, giving each phone number its own conversation history
- Apply PII guardrails to protect user data in both directions

### Step 6: Configure the Webhook URL in Meta

1. In the Meta App Dashboard, go to WhatsApp > Configuration
2. Set the **Callback URL** to:
   ```
   https://your-domain.com/v1/channels/whatsapp/webhook
   ```
3. Set the **Verify Token** to the same value as `WHATSAPP_VERIFY_TOKEN`
4. Subscribe to the **messages** webhook field

Meta will send a GET request to your URL with the verify token to confirm ownership. Astromesh handles this automatically.

### Step 7: Verify the Token

When you save the webhook configuration in Meta's dashboard, Meta sends a verification request:

```
GET /v1/channels/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=<your-token>&hub.challenge=<challenge>
```

Astromesh compares the `verify_token` from the query parameter against the configured `WHATSAPP_VERIFY_TOKEN`. If they match, it returns the challenge string and Meta confirms the webhook is active.

## Testing with ngrok

For local development, use [ngrok](https://ngrok.com/) to expose your local Astromesh instance to the internet:

```bash
# Start Astromesh
uv run uvicorn astromesh.api.main:app --reload --port 8000

# In another terminal, start ngrok
ngrok http 8000
```

ngrok provides a public HTTPS URL like `https://abc123.ngrok-free.app`. Use this as your webhook URL in the Meta dashboard:

```
https://abc123.ngrok-free.app/v1/channels/whatsapp/webhook
```

Remember that the ngrok URL changes each time you restart ngrok (unless you have a paid plan with reserved domains). Update the webhook URL in Meta's dashboard accordingly.

## How It Works Internally

### GET Webhook (Verification)

When Meta verifies ownership of the webhook URL:

1. Meta sends `GET /v1/channels/whatsapp/webhook` with query parameters `hub.mode`, `hub.verify_token`, and `hub.challenge`
2. The route handler calls `WhatsAppClient.verify_webhook(mode, token, challenge)`
3. If `mode == "subscribe"` and `token` matches the configured verify token, the handler returns the `challenge` value as a plain text response
4. Meta confirms the webhook is active

### POST Webhook (Incoming Messages)

When a user sends a message:

1. Meta sends `POST /v1/channels/whatsapp/webhook` with a JSON payload containing the message
2. The route handler validates the request signature using HMAC-SHA256:
   - The `X-Hub-Signature-256` header contains `sha256=<signature>`
   - The handler computes `HMAC-SHA256(app_secret, raw_body)` and compares it to the provided signature
   - If the signature does not match, the request is rejected with 403
3. `WhatsAppClient.parse_webhook(payload)` extracts the sender phone number and message text
4. The agent is executed in a **background task** — the route returns 200 to Meta immediately
5. `AgentRuntime.run(agent_name, message_text, session_id=phone_number)` runs the full pipeline
6. `WhatsAppClient.send_message(phone_number, response_text)` sends the result back via the Meta Graph API
7. If the agent execution fails, a generic error message is sent to the user

The background task design is critical: Meta requires a response within 5 seconds, but agent execution (LLM calls, tool use, multi-step reasoning) can take much longer. By returning 200 immediately and processing in the background, the webhook stays healthy.

## Rate Limiting

The channel configuration supports rate limiting to prevent abuse:

```yaml
channels:
  whatsapp:
    # ... credentials ...
    rate_limit:
      window_seconds: 60
      max_messages: 30
```

This limits each phone number to 30 messages per 60-second window. Messages that exceed the limit receive a polite "please wait" response instead of triggering agent execution.

## Message Types

Currently supported:

- **Text messages** — fully supported, processed through the agent pipeline

Planned for future releases:

- Image, audio, and document messages (media)
- Interactive messages (buttons, lists)
- Read receipts and typing indicators

## Production Deployment

For production use:

1. **Use HTTPS** — Meta requires a valid SSL certificate on the webhook URL. Use a reverse proxy (nginx, Caddy) or a cloud load balancer with TLS termination.

2. **Stable webhook URL** — Unlike ngrok, your production URL must not change. Use a domain you control.

3. **Permanent access token** — The temporary token from Meta's dashboard expires. Create a System User in Meta Business Suite and generate a permanent token.

4. **Set the app secret** — Always configure `WHATSAPP_APP_SECRET` in production to enable signature validation.

5. **Docker or Kubernetes** — Deploy using the standard Astromesh Docker image or Helm chart. The WhatsApp channel adapter is included by default.

6. **Monitor the webhook** — Use the observability stack to track webhook latency, agent execution time, and error rates. See the [Observability Stack](/astromech-platform/advanced/observability/) guide.

## Troubleshooting

### Webhook verification fails

- Confirm that `WHATSAPP_VERIFY_TOKEN` matches the verify token in Meta's dashboard exactly (no trailing spaces, correct case)
- Ensure the Astromesh instance is running and reachable at the configured callback URL
- Check that the URL path is exactly `/v1/channels/whatsapp/webhook`

### Signature validation fails (403 errors)

- Verify that `WHATSAPP_APP_SECRET` matches the App Secret in Meta's dashboard (Settings > Basic)
- If you recently rotated the app secret, update the environment variable and restart Astromesh
- Temporarily remove `app_secret` from `channels.yaml` to skip validation (development only)

### Agent not responding

- Check that the `default_agent` in `channels.yaml` matches an agent file in `config/agents/`
- Review the Astromesh logs for agent execution errors
- Test the agent directly via the REST API: `POST /v1/agents/whatsapp-assistant/run`
- Verify that the configured LLM provider is reachable and has valid credentials

### Rate limit hit

- The user sees a "please wait" message instead of an agent response
- Adjust `rate_limit.window_seconds` and `rate_limit.max_messages` in `channels.yaml`
- Check if a single user is sending excessive messages (potential abuse)

### Meta retries the webhook

- Meta retries if it does not receive a 200 response within approximately 5 seconds
- This usually means the route handler is blocking on agent execution instead of using a background task
- Check Astromesh logs for errors in the webhook route — the handler should return 200 before the agent runs
