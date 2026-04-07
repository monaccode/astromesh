---
title: Webhook Event Dispatcher
description: How Astromesh classifies and routes incoming Meta webhook events — user messages vs. status updates vs. system events.
---

# Webhook Event Dispatcher

When Meta delivers a webhook POST to your agent's endpoint, the payload can
contain many different types of events — user messages, delivery receipts,
account updates, template status changes, and more. Astromesh automatically
classifies each event so only genuine user messages reach your agent, while
other events are logged and surfaced in the Channel Activity panel.

## How it works

Every Meta webhook payload wraps events in a `change["field"]` key that
identifies the event category. Astromesh inspects this field before any
parsing:

```
POST /v1/agents/{agent}/channels/whatsapp/webhook
  └─ entry[].changes[]
       ├─ field="messages" + has "messages" key   → agent conversation
       ├─ field="messages" + has "statuses" key   → delivery/read receipt
       └─ field=anything else                     → system event
```

### User messages → agent conversation

When `field="messages"` and the payload contains a `messages` array, Astromesh:

1. Extracts the sender's display name from the parallel `contacts` array
2. Parses text and media via `parse_incoming()`
3. Emits an `in` SSE event (visible in the Channel Activity panel)
4. Runs `_process_agent_message()` in the background, which:
   - Builds the multimodal query
   - Calls `runtime.run()` with `session_id="whatsapp_{sender_phone}"` and `context={"contact_name": "..."}`
   - Sends the agent's reply back to WhatsApp
   - Emits an `out` SSE event

### Contact name in sessions

The agent session carries the contact's WhatsApp display name in the runtime
context. You can reference it in your system prompt for personalized responses:

```yaml
prompts:
  system: |
    You are a helpful assistant.
    {% if contact_name %}Address the user as {{ contact_name }}.{% endif %}
```

:::note
Contact name availability depends on the user's WhatsApp privacy settings.
Always handle the case where it is absent — the field will be `None` if Meta
does not include it.
:::

### Status updates (delivery receipts)

When `value["statuses"]` is present, the built-in `StatusUpdateHandler` runs.
It logs each status and emits a `system` SSE event — **no message is sent to
the agent**. Status types: `sent`, `delivered`, `read`, `failed`.

### System events (all other fields)

Any `change["field"]` other than `"messages"` (e.g. `account_update`,
`message_template_status_update`, `flows`) is routed to `WebhookEventDispatcher`.
If no handler is registered for that field, `DefaultWebhookEventHandler` runs:
it logs the event and emits a `system` SSE event.

## Registering a custom handler

To react to a specific Meta webhook field, implement the `WebhookEventHandler`
protocol and register it at application startup:

```python
from astromesh.channels.webhook_dispatcher import webhook_dispatcher


class TemplateStatusHandler:
    async def handle(self, field: str, value: dict, agent_name: str) -> None:
        template_name = value.get("message_template", {}).get("name", "")
        new_status = value.get("event", "")
        # your logic here — e.g. update a database, send an alert


webhook_dispatcher.register("message_template_status_update", TemplateStatusHandler())
```

Register handlers before the first webhook arrives (e.g. in your startup hook
or app factory).

## Meta webhook fields reference

| Field | Description | Default behavior |
|-------|-------------|------------------|
| `messages` (with messages) | User-sent text or media | → Agent conversation |
| `messages` (with statuses) | Delivery/read/failed receipts | Log + system SSE |
| `account_alerts` | Platform alerts for your account | Log + system SSE |
| `account_review_update` | Account review status change | Log + system SSE |
| `account_settings_update` | Business account setting change | Log + system SSE |
| `account_update` | Account verification update | Log + system SSE |
| `automatic_events` | Automated platform events | Log + system SSE |
| `business_capability_update` | Business capability change | Log + system SSE |
| `business_status_update` | Business status change | Log + system SSE |
| `calls` | Incoming call events | Log + system SSE |
| `flows` | WhatsApp Flows interactions | Log + system SSE |
| `message_echoes` | Copies of messages sent by business | Log + system SSE |
| `message_template_components_update` | Template component update | Log + system SSE |
| `message_template_quality_update` | Template quality rating change | Log + system SSE |
| `message_template_status_update` | Template approval/rejection | Log + system SSE |
| `messaging_handovers` | Handover protocol events | Log + system SSE |
| `phone_number_name_update` | Phone number display name change | Log + system SSE |
| `phone_number_quality_update` | Phone number quality rating | Log + system SSE |
| `security` | Security-related events | Log + system SSE |
| `template_category_update` | Template category change | Log + system SSE |
| All others | Any unregistered field | Log + system SSE |

## Viewing events in Channel Activity

All `system` events appear in the **Channel Activity** sidebar panel in
Astromesh Cortex with a distinct style (neither incoming nor outgoing). This
lets you monitor delivery receipts, account events, and custom handler activity
without cluttering the conversation log.
