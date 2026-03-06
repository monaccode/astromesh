# WhatsApp Integration Guide

## Overview

Astromech supports WhatsApp as a messaging channel through the Meta Cloud API. Incoming WhatsApp messages are received via a webhook, routed to a configured agent for processing, and the agent's response is sent back to the user through the WhatsApp Business API.

The integration consists of three components:

- **WhatsApp Client** (`astromech/channels/whatsapp.py`) — Handles webhook verification, signature validation, payload parsing, and outbound message delivery via the Meta Graph API.
- **Webhook Route** (`astromech/api/routes/whatsapp.py`) — FastAPI endpoints that receive Meta webhook events and dispatch messages to the agent runtime in the background.
- **Channel Configuration** (`config/channels.yaml`) — Declares credentials, the default agent, and rate limiting settings.

```
WhatsApp User
    |
    v
Meta Cloud API
    |
    v  (POST /v1/channels/whatsapp/webhook)
Astromech Webhook Route
    |
    v
Agent Runtime (whatsapp-assistant)
    |
    v  (Graph API)
Meta Cloud API
    |
    v
WhatsApp User
```

## Prerequisites

- A Meta Business Account (free at [business.facebook.com](https://business.facebook.com))
- A Meta Developer App with the WhatsApp product added ([developers.facebook.com](https://developers.facebook.com))
- A phone number registered with WhatsApp Business
- Astromech platform running (local or deployed)
- Python 3.12+ and [uv](https://docs.astral.sh/uv/)

## Quick Start

1. **Install Astromech** (if not already done):

   ```bash
   uv sync
   ```

2. **Set environment variables** with your Meta app credentials:

   ```bash
   export WHATSAPP_VERIFY_TOKEN="my-secret-verify-token"
   export WHATSAPP_ACCESS_TOKEN="EAAx..."
   export WHATSAPP_PHONE_NUMBER_ID="106..."
   export WHATSAPP_APP_SECRET="abc123..."   # optional but recommended
   ```

3. **Start the Astromech server**:

   ```bash
   uv run uvicorn astromech.api.main:app --host 0.0.0.0 --port 8000
   ```

4. **Expose your local server** using ngrok (for development):

   ```bash
   ngrok http 8000
   ```

5. **Configure the webhook in Meta Developer Dashboard**:
   - Go to your app > WhatsApp > Configuration
   - Set the Callback URL to `https://<your-ngrok-url>/v1/channels/whatsapp/webhook`
   - Set the Verify Token to the same value as `WHATSAPP_VERIFY_TOKEN`
   - Subscribe to the `messages` webhook field

6. **Send a test message** from your WhatsApp phone to the registered business number. The `whatsapp-assistant` agent will process it and reply.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `WHATSAPP_VERIFY_TOKEN` | Yes | A secret token you create for Meta webhook verification. Must match the value entered in the Meta Developer Dashboard. |
| `WHATSAPP_ACCESS_TOKEN` | Yes | Access token from Meta for calling the WhatsApp Cloud API. Found under your app's WhatsApp > API Setup page. |
| `WHATSAPP_PHONE_NUMBER_ID` | Yes | The phone number ID assigned to your WhatsApp Business number. Found under WhatsApp > API Setup. |
| `WHATSAPP_APP_SECRET` | No | Your Meta app's secret key. Used to validate `X-Hub-Signature-256` headers on incoming webhooks. Strongly recommended for production. |

## Agent Configuration

WhatsApp messages are routed to the agent specified in `config/channels.yaml` (default: `whatsapp-assistant`). The sample agent definition lives at `config/agents/whatsapp-assistant.agent.yaml`:

```yaml
apiVersion: astromech/v1
kind: Agent
metadata:
  name: whatsapp-assistant
  version: "1.0.0"
  namespace: messaging
  labels:
    channel: whatsapp
    tier: production

spec:
  identity:
    display_name: "WhatsApp Assistant"
    description: "Conversational assistant optimized for WhatsApp messaging"

  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"
      endpoint: "http://ollama:11434"
      parameters:
        temperature: 0.4
        max_tokens: 1024

  prompts:
    system: |
      You are a friendly and helpful WhatsApp assistant. Keep your responses concise
      and conversational — max 1-2 short paragraphs. Use a warm, approachable tone.

      Guidelines:
      - Be direct and get to the point quickly
      - Use simple language; avoid jargon
      - If you don't know something, say so and offer alternatives
      - Never share sensitive information in chat

  orchestration:
    pattern: react
    max_iterations: 5
    timeout_seconds: 30

  memory:
    conversational:
      backend: sqlite
      strategy: sliding_window
      max_turns: 30
      ttl: 86400

  guardrails:
    input:
      - type: pii_detection
        action: redact
      - type: max_length
        max_chars: 2000
    output:
      - type: pii_detection
        action: redact
```

Key considerations for WhatsApp agents:

- **Keep `max_tokens` low** (1024 or less). WhatsApp messages display best when short.
- **Set `timeout_seconds`**. WhatsApp users expect fast replies; 30 seconds is a reasonable upper bound.
- **Enable PII guardrails**. WhatsApp messages often contain personal data. The `pii_detection` guardrail with `redact` action prevents the agent from echoing sensitive information.

To use a different agent, update the `default_agent` field in `config/channels.yaml`.

## Webhook Setup

### Development (ngrok)

1. Install [ngrok](https://ngrok.com/download) and authenticate:

   ```bash
   ngrok config add-authtoken <your-ngrok-token>
   ```

2. Start Astromech on port 8000, then start ngrok:

   ```bash
   ngrok http 8000
   ```

3. Copy the `https://` forwarding URL from ngrok output (e.g., `https://a1b2c3d4.ngrok-free.app`).

4. In the Meta Developer Dashboard under WhatsApp > Configuration:
   - **Callback URL**: `https://a1b2c3d4.ngrok-free.app/v1/channels/whatsapp/webhook`
   - **Verify Token**: the value of your `WHATSAPP_VERIFY_TOKEN` environment variable
   - Click **Verify and Save**

5. Under Webhook Fields, subscribe to **messages**.

Note: ngrok URLs change each time you restart. Update the callback URL in the Meta dashboard after each restart, or use a paid ngrok plan with a stable subdomain.

### Production

1. Deploy Astromech behind a reverse proxy (nginx, Caddy, etc.) with a valid TLS certificate. Meta requires HTTPS for webhooks.

2. Set the Callback URL in the Meta Developer Dashboard to your production endpoint:

   ```
   https://api.yourdomain.com/v1/channels/whatsapp/webhook
   ```

3. Set the Verify Token to match your `WHATSAPP_VERIFY_TOKEN` environment variable and click **Verify and Save**.

4. Subscribe to the **messages** webhook field.

5. Set `WHATSAPP_APP_SECRET` to enable signature validation on incoming webhook requests (see Security Considerations).

## Message Flow

```
1. User sends a WhatsApp message
2. Meta Cloud API delivers a POST to /v1/channels/whatsapp/webhook
3. Webhook route validates X-Hub-Signature-256 (if app secret is configured)
4. Webhook route parses the payload and extracts text messages
5. Each message is dispatched to the agent runtime as a background task
6. Agent runtime runs the configured agent (whatsapp-assistant)
   - Loads conversation memory (keyed by wa_<phone_number>)
   - Renders the system prompt
   - Executes the orchestration pattern (ReAct)
   - Applies guardrails on input and output
7. Agent response is sent back via Meta Graph API POST to /<phone_number_id>/messages
8. User receives the reply in WhatsApp
```

## Channel Configuration

Channel settings are defined in `config/channels.yaml`:

```yaml
channels:
  whatsapp:
    # WhatsApp Business Cloud API settings
    verify_token: "${WHATSAPP_VERIFY_TOKEN}"
    access_token: "${WHATSAPP_ACCESS_TOKEN}"
    phone_number_id: "${WHATSAPP_PHONE_NUMBER_ID}"
    app_secret: "${WHATSAPP_APP_SECRET}"

    # Which agent handles WhatsApp conversations
    default_agent: "whatsapp-assistant"

    # Rate limiting for outgoing messages
    rate_limit:
      window_seconds: 60
      max_messages: 30
```

| Field | Description |
|-------|-------------|
| `verify_token` | Token for Meta webhook verification handshake |
| `access_token` | Bearer token for outbound Graph API calls |
| `phone_number_id` | Phone number ID for sending messages |
| `app_secret` | App secret for webhook signature validation |
| `default_agent` | Name of the agent YAML (must exist in `config/agents/`) |
| `rate_limit.window_seconds` | Rolling window duration for rate limiting |
| `rate_limit.max_messages` | Maximum outbound messages per window |

Credential values use the `${VAR_NAME}` syntax and are resolved from environment variables at startup.

## Troubleshooting

### Webhook verification fails

- Confirm that `WHATSAPP_VERIFY_TOKEN` matches the value entered in the Meta Developer Dashboard.
- Verify the callback URL ends with `/v1/channels/whatsapp/webhook` and is reachable over HTTPS.
- Check Astromech server logs for the incoming verification request.

### Messages not arriving

- Confirm the **messages** webhook field is subscribed in the Meta dashboard.
- Check that your ngrok tunnel (or production endpoint) is running and accessible.
- Look at Meta's webhook test tool in the dashboard to see delivery status.
- Verify the phone number is registered and the WhatsApp Business account is active.

### Agent not responding

- Check that the agent specified in `config/channels.yaml` (`default_agent`) has a matching YAML file in `config/agents/`.
- Verify the LLM provider endpoint is reachable (e.g., Ollama is running).
- Review Astromech logs for errors in background task processing.
- Confirm `WHATSAPP_ACCESS_TOKEN` is valid and has not expired.

### Rate limiting

- Meta enforces rate limits on the WhatsApp Cloud API. If you receive 429 responses, reduce message throughput.
- The `rate_limit` section in `config/channels.yaml` controls Astromech's outbound rate. Adjust `max_messages` and `window_seconds` as needed.

### Signature validation errors

- Ensure `WHATSAPP_APP_SECRET` matches your app's secret in the Meta Developer Dashboard (under App Settings > Basic).
- If you do not need signature validation during development, leave `WHATSAPP_APP_SECRET` unset. The client will skip validation when no secret is configured.

## Security Considerations

- **Always use HTTPS in production.** Meta requires a valid TLS certificate for webhook URLs. Use a reverse proxy with automatic certificate management (e.g., Caddy, Certbot with nginx).
- **Enable signature validation.** Set `WHATSAPP_APP_SECRET` to your Meta app secret. The webhook route validates the `X-Hub-Signature-256` header on every incoming request, rejecting payloads with an invalid or missing signature.
- **Enable PII guardrails.** WhatsApp messages frequently contain phone numbers, names, and other personal data. Configure `pii_detection` guardrails on both input and output to redact sensitive information before it reaches the LLM or is stored in memory.
- **Apply rate limiting.** Use the `rate_limit` configuration in `config/channels.yaml` to cap outbound messages per time window. This protects against runaway loops and excessive API usage.
- **Rotate access tokens.** Meta access tokens can expire. Use System User tokens for long-lived production deployments and rotate them periodically.
- **Restrict network access.** In production, restrict inbound traffic to Meta's webhook IP ranges where possible.
