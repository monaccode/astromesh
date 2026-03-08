# WhatsApp Channel Integration — Design Document

**Date:** 2026-03-06
**Status:** Approved
**Version:** 0.2.0

## Summary

Add a WhatsApp channel adapter to Astromesh platform using Meta's WhatsApp Business Cloud API. This enables any configured agent to handle WhatsApp conversations with zero changes to the existing runtime, memory, or orchestration layers.

## Architecture

```
WhatsApp User
    │
    ▼
Meta Cloud API ──webhook──► POST /v1/channels/whatsapp/webhook
                                │
                                ▼
                          WhatsAppClient.parse_webhook()
                                │
                                ▼
                          AgentRuntime.run(
                              agent_name=config.default_agent,
                              query=message_text,
                              session_id=phone_number
                          )
                                │
                                ▼
                          WhatsAppClient.send_message(phone, response)
                                │
                                ▼
                          POST graph.facebook.com/v21.0/{phone_id}/messages
                                │
                                ▼
                          WhatsApp User receives response
```

## Components

### 1. WhatsAppClient (`astromesh/channels/whatsapp.py`)

Handles all Meta API interaction:

- **`parse_webhook(payload)`** — Extract sender phone number and message text from Meta webhook payload
- **`send_message(to, text)`** — Send text message via Meta Cloud API
- **`verify_webhook(mode, token, challenge)`** — Handle Meta webhook verification handshake
- **`validate_signature(payload, signature)`** — HMAC-SHA256 signature verification for security

Configuration via environment variables:
- `WHATSAPP_VERIFY_TOKEN` — Webhook verification token (you choose this)
- `WHATSAPP_ACCESS_TOKEN` — Meta API access token
- `WHATSAPP_PHONE_NUMBER_ID` — Business phone number ID
- `WHATSAPP_APP_SECRET` — App secret for signature validation (optional)

### 2. Webhook Route (`astromesh/api/routes/whatsapp.py`)

Two endpoints:

- **`GET /v1/channels/whatsapp/webhook`** — Meta verification (returns challenge)
- **`POST /v1/channels/whatsapp/webhook`** — Receive messages, run agent, respond

### 3. Channel Configuration (`config/channels.yaml`)

```yaml
channels:
  whatsapp:
    verify_token: "${WHATSAPP_VERIFY_TOKEN}"
    access_token: "${WHATSAPP_ACCESS_TOKEN}"
    phone_number_id: "${WHATSAPP_PHONE_NUMBER_ID}"
    app_secret: "${WHATSAPP_APP_SECRET}"
    default_agent: "whatsapp-assistant"
```

### 4. Sample Agent (`config/agents/whatsapp-assistant.agent.yaml`)

A conversational agent optimized for WhatsApp:
- Short, concise responses (WhatsApp UX)
- Sliding window memory (keyed by phone number)
- ReAct pattern for tool use
- Input/output guardrails (PII redaction)

## Data Flow

1. Meta sends webhook POST with message payload
2. Route validates signature (if app_secret configured)
3. WhatsAppClient parses payload → extracts `phone_number`, `message_text`
4. Calls `runtime.run(agent_name, message_text, session_id=phone_number)`
5. Agent pipeline executes (memory, LLM, tools, guardrails)
6. WhatsAppClient sends response text back via Meta API
7. Returns 200 to Meta (important: must respond quickly)

## Error Handling

- If agent execution fails → send generic error message to user
- If Meta API call fails → log error, retry with exponential backoff
- Webhook must return 200 within 5s or Meta retries → use background task for agent execution

## Security

- HMAC-SHA256 signature verification on incoming webhooks
- PII guardrails apply automatically via agent config
- Access token stored in env vars, never in config files

## What We Don't Touch

- AgentRuntime, Agent, MemoryManager — unchanged
- OrchestrationPatterns — unchanged
- ModelRouter, Providers — unchanged
- GuardrailsEngine — unchanged
- Existing API routes — unchanged

## Future Extensions (Not in scope)

- Media messages (images, audio, documents)
- Interactive messages (buttons, lists)
- Multi-agent routing based on intent
- Read receipts and typing indicators
