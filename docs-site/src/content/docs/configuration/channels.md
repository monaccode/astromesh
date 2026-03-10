---
title: Channels
description: Configure external messaging platform integrations
---

Channels connect external messaging platforms to the Astromesh agent runtime. When a user sends a message through a channel (e.g., WhatsApp), the channel adapter receives it via a webhook, forwards it to the configured agent, and sends the agent's response back through the platform.

## File Location

Channel configuration lives at `config/channels.yaml` (development) or `/etc/astromesh/channels.yaml` (production). Unlike other Astromesh config files, `channels.yaml` does not use the `apiVersion`/`kind` header — it uses a simpler structure keyed by channel name.

## How Channels Work

The message flow through a channel follows this sequence:

```
External User
    |
    v
Messaging Platform (Meta Cloud API, etc.)
    |
    v  (POST webhook)
Astromesh Channel Adapter
    |  - Validates webhook signature
    |  - Parses the incoming payload
    |  - Extracts the message content
    v
Agent Runtime
    |  - Loads conversation memory (keyed by sender ID)
    |  - Renders system prompt
    |  - Executes orchestration pattern
    |  - Applies input/output guardrails
    v
Channel Adapter
    |  - Formats the response for the platform
    |  - Sends via platform API
    v
External User receives the reply
```

The webhook route responds to the messaging platform immediately (within the platform's timeout window), while agent execution runs as a background task. For WhatsApp, this means Astromesh responds to Meta within 5 seconds as required, and the agent's reply is sent asynchronously.

## WhatsApp Channel

WhatsApp is the first supported channel in Astromesh. It integrates with the Meta WhatsApp Business Cloud API.

### Configuration

```yaml
channels:
  whatsapp:
    # WhatsApp Business Cloud API credentials
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

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `verify_token` | Yes | Token for Meta webhook verification. When Meta sends a GET request to verify your webhook, Astromesh checks that the token in the request matches this value. |
| `access_token` | Yes | Bearer token for outbound Graph API calls. Used to send messages back to WhatsApp users. |
| `phone_number_id` | Yes | The phone number ID assigned to your WhatsApp Business account. Messages are sent from this number. |
| `app_secret` | No | App secret for validating the `X-Hub-Signature-256` header on incoming webhooks. Strongly recommended for production. |
| `default_agent` | Yes | The `metadata.name` of the agent that handles WhatsApp conversations. Must match an agent YAML file in `config/agents/`. |
| `rate_limit.window_seconds` | No | Rolling window duration in seconds for outbound rate limiting. Default: `60`. |
| `rate_limit.max_messages` | No | Maximum number of outbound messages allowed per window. Default: `30`. |

### Environment Variables

Credential values use the `${VAR_NAME}` syntax and are resolved from environment variables at startup. Set these before starting Astromesh:

```bash
export WHATSAPP_VERIFY_TOKEN="my-secret-verify-token"
export WHATSAPP_ACCESS_TOKEN="EAAx..."
export WHATSAPP_PHONE_NUMBER_ID="106..."
export WHATSAPP_APP_SECRET="abc123..."
```

| Variable | Description |
|----------|-------------|
| `WHATSAPP_VERIFY_TOKEN` | A secret string you create. Must match the verify token entered in the Meta Developer Dashboard when setting up the webhook. |
| `WHATSAPP_ACCESS_TOKEN` | Permanent access token from Meta Business settings. Found under your app's WhatsApp > API Setup page. Use a System User token for production. |
| `WHATSAPP_PHONE_NUMBER_ID` | The phone number ID from your WhatsApp Business account. Found under WhatsApp > API Setup in the Meta Developer Dashboard. |
| `WHATSAPP_APP_SECRET` | Your Meta app's secret key (under App Settings > Basic). Used to validate `X-Hub-Signature-256` signatures on incoming webhook payloads. |

### Agent Routing

The `default_agent` field determines which agent processes WhatsApp messages. The value must match the `metadata.name` of an agent defined in `config/agents/`:

```yaml
# config/channels.yaml
channels:
  whatsapp:
    default_agent: "whatsapp-assistant"
```

```yaml
# config/agents/whatsapp-assistant.agent.yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: whatsapp-assistant    # Must match default_agent
```

Conversation memory is keyed by the sender's phone number (`wa_<phone_number>`), so each WhatsApp user gets an independent conversation history.

### Rate Limiting

The `rate_limit` section controls outbound message throttling to stay within Meta's API limits:

```yaml
rate_limit:
  window_seconds: 60
  max_messages: 30
```

This configuration allows a maximum of 30 outbound messages per 60-second rolling window. When the limit is reached, messages are queued until the window resets. Adjust these values based on your WhatsApp Business tier and expected traffic volume.

### Webhook Endpoints

Astromesh exposes two endpoints for the WhatsApp webhook:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v1/channels/whatsapp/webhook` | Webhook verification. Meta sends a GET request with a challenge token during setup. Astromesh validates the verify token and returns the challenge. |
| `POST` | `/v1/channels/whatsapp/webhook` | Message delivery. Meta sends incoming messages as POST requests with a JSON payload. Astromesh validates the signature, parses the message, and dispatches it to the agent runtime. |

### Multimedia Support

The WhatsApp channel supports receiving multimedia messages:

| Media Type | Handling |
|------------|----------|
| Images | Downloaded from Meta servers, base64-encoded, and sent to the agent as a vision query. Requires a vision-capable model (e.g., `llava:7b`). |
| Audio | Downloaded and described as text (format, size) for the agent. |
| Video | Downloaded and described as text for the agent. |
| Documents | Downloaded and described as text with the filename for the agent. |

No media is stored on disk. Media bytes are processed in-memory and discarded after the agent responds.

## Future Channels

WhatsApp is the first supported channel. The channel architecture is designed to be extensible — additional channels (Slack, Telegram, Discord, etc.) will follow the same pattern: a channel adapter, a webhook route, and a section in `channels.yaml`.

Each future channel will have its own key under `channels:` with platform-specific configuration:

```yaml
channels:
  whatsapp:
    # ... WhatsApp config

  slack:
    # ... future Slack config

  telegram:
    # ... future Telegram config
```
