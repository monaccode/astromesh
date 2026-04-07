# WhatsApp Webhook Dispatcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the naïve single-path webhook receiver with a two-phase dispatcher that classifies every incoming Meta webhook event by `change["field"]`, routes user messages to the agent, enriches them with the contact's display name, and forwards all other events through a `WebhookEventHandler` protocol for future extensibility.

**Architecture:** The POST endpoint iterates `entry[].changes[]` and inspects `change["field"]` before any parsing. If the field is `"messages"` and contains actual user messages, the existing `parse_incoming → _process_agent_message` pipeline runs (enriched with contact name). Everything else is dispatched to `WebhookEventDispatcher`, which looks up a registered handler or falls back to the built-in default (log + SSE emit). Status updates (`value["statuses"]`) are handled by a built-in `StatusUpdateHandler`.

**Tech Stack:** Python 3.12, FastAPI, existing `ChannelEventBus`, `ChannelMessage` dataclass, `ChannelAdapter` ABC.

---

## Files

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `astromesh/channels/base.py` | Add `contact_name: str \| None` to `ChannelMessage` |
| Create | `astromesh/channels/webhook_dispatcher.py` | `WebhookEventHandler` protocol, `WebhookEventDispatcher`, `DefaultWebhookEventHandler`, `StatusUpdateHandler` |
| Modify | `astromesh/api/routes/agent_channels.py` | Two-phase dispatch loop, contact name extraction, pass `metadata` to `runtime.run()` |
| Modify | `astromesh/channels/whatsapp.py` | Update `parse_incoming` to accept the `value` dict (`change["value"]`) instead of the full payload — dispatcher already iterates entries/changes |
| Modify | `astromesh/channels/event_bus.py` | Add `"system"` to `direction` Literal |
| No change | `astromesh/runtime/engine.py` | `run()` already accepts `context: dict \| None` — use it for contact metadata |
| Create | `tests/test_webhook_dispatcher.py` | Unit tests for dispatcher, handlers, contact enrichment |
| Create | `docs-site/src/content/docs/advanced/webhook-events.md` | Developer docs for the dispatcher |

---

## Design Details

### Two-Phase Dispatch Logic

```
POST /v1/agents/{agent}/channels/whatsapp/webhook
  → for each change in payload["entry"][*]["changes"]:
      field = change["field"]
      value = change["value"]

      if field == "messages":
          if "messages" in value:          # user-initiated messages
              contacts = value.get("contacts", [])
              messages = parse_incoming(value)   # existing method
              enrich_with_contact_name(messages, contacts)
              for msg in messages:
                  emit_sse("in", msg)
                  background: _process_agent_message(msg)
          if "statuses" in value:          # delivery/read receipts
              dispatcher.dispatch("statuses", value, agent_name)
      else:
          dispatcher.dispatch(field, value, agent_name)

  → return {"status": "ok"}
```

### Contact Name Enrichment

Meta sends a `contacts` array parallel to `messages` in the same `value` object:
```json
{
  "messages": [{"from": "573001234567", ...}],
  "contacts": [{"profile": {"name": "Juan Pérez"}, "wa_id": "573001234567"}]
}
```

The dispatcher builds a lookup `{wa_id: name}` and sets `msg.contact_name` after `parse_incoming` returns.

### WebhookEventHandler Protocol

```python
# astromesh/channels/webhook_dispatcher.py

class WebhookEventHandler(Protocol):
    async def handle(self, field: str, value: dict, agent_name: str) -> None: ...

class DefaultWebhookEventHandler:
    """Fallback: log + emit SSE system event."""
    async def handle(self, field: str, value: dict, agent_name: str) -> None:
        logger.info("webhook_event field=%s agent=%s", field, agent_name)
        channel_event_bus.emit(ChannelEvent.create(
            agent=agent_name, channel="whatsapp", direction="system",
            sender="meta", text=f"[{field}] event received",
        ))

class StatusUpdateHandler:
    """Built-in handler for delivery/read/failed status updates."""
    async def handle(self, field: str, value: dict, agent_name: str) -> None:
        for status in value.get("statuses", []):
            status_type = status.get("status", "unknown")
            recipient = status.get("recipient_id", "unknown")
            msg_id = status.get("id", "")
            logger.info("message_status=%s recipient=%s msg_id=%s", status_type, recipient, msg_id)
            channel_event_bus.emit(ChannelEvent.create(
                agent=agent_name, channel="whatsapp", direction="system",
                sender=recipient, text=f"[status:{status_type}] message {msg_id}",
            ))

class WebhookEventDispatcher:
    def __init__(self):
        self._handlers: dict[str, WebhookEventHandler] = {}
        self._default = DefaultWebhookEventHandler()
        self.register("statuses", StatusUpdateHandler())

    def register(self, field: str, handler: WebhookEventHandler) -> None:
        self._handlers[field] = handler

    async def dispatch(self, field: str, value: dict, agent_name: str) -> None:
        handler = self._handlers.get(field, self._default)
        await handler.handle(field, value, agent_name)
```

### Session Context

`_process_agent_message` passes contact name via the existing `context` parameter of `runtime.run()` (`astromesh/runtime/engine.py:273`):

```python
result = await _runtime.run(
    agent_name=agent_name,
    query=query,
    session_id=f"whatsapp_{message.sender_id}",
    context={"contact_name": message.contact_name} if message.contact_name else None,
)
```

`runtime.run()` already forwards `context` to `agent.run()`. No changes needed in `engine.py`. The agent prompt can reference it via `{{contact_name}}` interpolation (future) or it is available for custom tool implementations.

### ChannelEvent direction

Add `"system"` to the `direction` Literal in `event_bus.py`:

```python
direction: Literal["in", "out", "system"]
```

`"system"` events are visible in the ChannelActivityPanel with a distinct style (not a user message, not an agent reply).

---

## Tasks

### Task 1: Add `contact_name` to `ChannelMessage` + `"system"` direction to `ChannelEvent`

**Files:**
- Modify: `astromesh/channels/base.py`
- Modify: `astromesh/channels/event_bus.py`
- Test: `tests/test_webhook_dispatcher.py` (initial file)

- [ ] **Step 1: Read current `ChannelMessage` dataclass**

```python
# astromesh/channels/base.py — current ChannelMessage
@dataclass
class ChannelMessage:
    sender_id: str
    text: str | None
    media: list[MediaAttachment]
    message_id: str
    timestamp: str
    channel: str
    raw_payload: dict
```

- [ ] **Step 2: Add `contact_name` field**

```python
@dataclass
class ChannelMessage:
    sender_id: str
    text: str | None
    media: list[MediaAttachment]
    message_id: str
    timestamp: str
    channel: str
    raw_payload: dict
    contact_name: str | None = None   # ← new, default None for backwards compat
```

- [ ] **Step 3: Add `"system"` to `ChannelEvent.direction`**

In `astromesh/channels/event_bus.py`, find the `direction` field:
```python
# before
direction: Literal["in", "out"]
# after
direction: Literal["in", "out", "system"]
```

- [ ] **Step 4: Write failing test for contact_name field**

Create `tests/test_webhook_dispatcher.py`:
```python
from astromesh.channels.base import ChannelMessage, MediaAttachment

def test_channel_message_contact_name_defaults_to_none():
    msg = ChannelMessage(
        sender_id="573001234567",
        text="hola",
        media=[],
        message_id="wamid.abc",
        timestamp="1712500000",
        channel="whatsapp",
        raw_payload={},
    )
    assert msg.contact_name is None

def test_channel_message_accepts_contact_name():
    msg = ChannelMessage(
        sender_id="573001234567",
        text="hola",
        media=[],
        message_id="wamid.abc",
        timestamp="1712500000",
        channel="whatsapp",
        raw_payload={},
        contact_name="Juan Pérez",
    )
    assert msg.contact_name == "Juan Pérez"
```

- [ ] **Step 5: Run tests**

```bash
cd D:/monaccode/astromesh
uv run pytest tests/test_webhook_dispatcher.py -v
```

Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add astromesh/channels/base.py astromesh/channels/event_bus.py tests/test_webhook_dispatcher.py
git commit -m "feat(channels): add contact_name to ChannelMessage + system direction to ChannelEvent"
```

---

### Task 2: Create `WebhookEventDispatcher`

**Files:**
- Create: `astromesh/channels/webhook_dispatcher.py`
- Test: `tests/test_webhook_dispatcher.py`

- [ ] **Step 1: Write failing tests first**

Append to `tests/test_webhook_dispatcher.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from astromesh.channels.webhook_dispatcher import (
    WebhookEventDispatcher,
    DefaultWebhookEventHandler,
    StatusUpdateHandler,
)

@pytest.mark.asyncio
async def test_dispatcher_uses_default_for_unknown_field():
    dispatcher = WebhookEventDispatcher()
    default_mock = AsyncMock()
    dispatcher._default = default_mock
    await dispatcher.dispatch("account_update", {"foo": "bar"}, "my-agent")
    default_mock.handle.assert_called_once_with("account_update", {"foo": "bar"}, "my-agent")

@pytest.mark.asyncio
async def test_dispatcher_uses_registered_handler():
    dispatcher = WebhookEventDispatcher()
    custom_handler = AsyncMock()
    dispatcher.register("flows", custom_handler)
    await dispatcher.dispatch("flows", {"data": 1}, "my-agent")
    custom_handler.handle.assert_called_once_with("flows", {"data": 1}, "my-agent")

@pytest.mark.asyncio
async def test_status_update_handler_logs_and_emits(mocker):
    mock_emit = mocker.patch("astromesh.channels.webhook_dispatcher.channel_event_bus.emit")
    handler = StatusUpdateHandler()
    value = {
        "statuses": [
            {"status": "delivered", "recipient_id": "573001234567", "id": "wamid.abc"}
        ]
    }
    await handler.handle("statuses", value, "my-agent")
    mock_emit.assert_called_once()
    event = mock_emit.call_args[0][0]
    assert event.direction == "system"
    assert "delivered" in event.text

@pytest.mark.asyncio
async def test_default_handler_emits_system_event(mocker):
    mock_emit = mocker.patch("astromesh.channels.webhook_dispatcher.channel_event_bus.emit")
    handler = DefaultWebhookEventHandler()
    await handler.handle("account_update", {}, "my-agent")
    mock_emit.assert_called_once()
    event = mock_emit.call_args[0][0]
    assert event.direction == "system"
    assert "account_update" in event.text
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_webhook_dispatcher.py -v
```

Expected: ImportError or FAIL (module doesn't exist yet)

- [ ] **Step 3: Implement `webhook_dispatcher.py`**

Create `astromesh/channels/webhook_dispatcher.py`:
```python
"""Webhook event dispatcher for per-agent channel webhooks.

Classifies incoming Meta webhook payloads by ``change["field"]`` and routes
them to the appropriate handler.  User messages (``field="messages"``) go
through the existing ``parse_incoming`` pipeline.  Everything else is
dispatched here, either to a registered custom handler or to the built-in
default (log + SSE system event).

Adding a handler for a new Meta webhook field:
    from astromesh.channels.webhook_dispatcher import webhook_dispatcher

    class MyHandler:
        async def handle(self, field: str, value: dict, agent_name: str) -> None:
            ...

    webhook_dispatcher.register("message_template_status_update", MyHandler())
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from astromesh.channels.event_bus import ChannelEvent, channel_event_bus

logger = logging.getLogger(__name__)


@runtime_checkable
class WebhookEventHandler(Protocol):
    """Protocol for handlers that process non-message Meta webhook events.

    Implement this protocol and register with ``WebhookEventDispatcher.register``
    to react to any Meta webhook field (e.g. ``message_template_status_update``,
    ``flows``, ``account_update``).
    """

    async def handle(self, field: str, value: dict, agent_name: str) -> None:
        """Process a single webhook event.

        Args:
            field: The Meta webhook ``change["field"]`` value (e.g. ``"account_update"``).
            value: The raw ``change["value"]`` dict from the Meta payload.
            agent_name: Name of the agent that owns this webhook.
        """
        ...


class DefaultWebhookEventHandler:
    """Fallback handler: logs the event and emits a ``system`` SSE event.

    This is used for any ``change["field"]`` that has no registered handler.
    It makes unhandled events visible in the ChannelActivityPanel without
    routing them to the agent.
    """

    async def handle(self, field: str, value: dict, agent_name: str) -> None:
        logger.info("unhandled_webhook_event field=%s agent=%s", field, agent_name)
        channel_event_bus.emit(
            ChannelEvent.create(
                agent=agent_name,
                channel="whatsapp",
                direction="system",
                sender="meta",
                text=f"[{field}] event received",
            )
        )


class StatusUpdateHandler:
    """Built-in handler for WhatsApp message delivery/read/failed status updates.

    Processes ``value["statuses"]`` entries and emits one ``system`` SSE event
    per status.  Does NOT route anything to the agent.

    Status types emitted by Meta: ``sent``, ``delivered``, ``read``, ``failed``.
    """

    async def handle(self, field: str, value: dict, agent_name: str) -> None:
        for status in value.get("statuses", []):
            status_type = status.get("status", "unknown")
            recipient = status.get("recipient_id", "unknown")
            msg_id = status.get("id", "")
            logger.info(
                "message_status_update status=%s recipient=%s msg_id=%s agent=%s",
                status_type, recipient, msg_id, agent_name,
            )
            channel_event_bus.emit(
                ChannelEvent.create(
                    agent=agent_name,
                    channel="whatsapp",
                    direction="system",
                    sender=recipient,
                    text=f"[status:{status_type}] message {msg_id}",
                )
            )


class WebhookEventDispatcher:
    """Dispatches Meta webhook events to registered handlers by ``change["field"]``.

    Usage::

        dispatcher = WebhookEventDispatcher()
        dispatcher.register("flows", MyFlowsHandler())
        await dispatcher.dispatch("flows", value, agent_name)

    The dispatcher ships with a ``StatusUpdateHandler`` pre-registered for
    ``"statuses"`` (delivery/read receipts) and falls back to
    ``DefaultWebhookEventHandler`` for any unregistered field.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, WebhookEventHandler] = {}
        self._default: WebhookEventHandler = DefaultWebhookEventHandler()
        self.register("statuses", StatusUpdateHandler())

    def register(self, field: str, handler: WebhookEventHandler) -> None:
        """Register a handler for a specific Meta webhook field.

        Args:
            field: The Meta ``change["field"]`` value to handle.
            handler: Any object implementing ``WebhookEventHandler``.
        """
        self._handlers[field] = handler

    async def dispatch(self, field: str, value: dict, agent_name: str) -> None:
        """Route an event to the appropriate handler.

        Args:
            field: The Meta ``change["field"]`` value.
            value: The raw ``change["value"]`` dict.
            agent_name: Name of the agent that owns this webhook.
        """
        handler = self._handlers.get(field, self._default)
        await handler.handle(field, value, agent_name)


# Module-level singleton used by the webhook endpoint.
# Import and use directly: ``from astromesh.channels.webhook_dispatcher import webhook_dispatcher``
webhook_dispatcher = WebhookEventDispatcher()
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_webhook_dispatcher.py -v
```

Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add astromesh/channels/webhook_dispatcher.py tests/test_webhook_dispatcher.py
git commit -m "feat(channels): add WebhookEventDispatcher with StatusUpdateHandler and DefaultWebhookEventHandler"
```

---

### Task 3: Two-phase dispatch in the endpoint + contact name enrichment

**Files:**
- Modify: `astromesh/api/routes/agent_channels.py`
- Test: `tests/test_agent_channels.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_agent_channels.py`:
```python
# Test: contact name is extracted from contacts array
@pytest.mark.asyncio
async def test_contact_name_extracted_from_payload(client, runtime_with_whatsapp_agent):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "contacts": [{"profile": {"name": "Juan Pérez"}, "wa_id": "573001234567"}],
                    "messages": [{
                        "from": "573001234567",
                        "id": "wamid.test123",
                        "timestamp": "1712500000",
                        "type": "text",
                        "text": {"body": "hola"},
                    }],
                },
            }],
        }],
    }
    with patch("astromesh.api.routes.agent_channels._runtime") as mock_runtime:
        mock_runtime.run = AsyncMock(return_value={"answer": "hola Juan"})
        resp = client.post(
            "/v1/agents/whatsapp-test/channels/whatsapp/webhook",
            json=payload,
            headers={"X-Hub-Signature-256": "sha256=bypass"},
        )
    assert resp.status_code == 200

# Test: status updates are dispatched, NOT sent to agent
@pytest.mark.asyncio
async def test_status_update_not_sent_to_agent(client, runtime_with_whatsapp_agent, mocker):
    mock_dispatch = mocker.patch(
        "astromesh.api.routes.agent_channels.webhook_dispatcher.dispatch",
        new_callable=AsyncMock,
    )
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "statuses": [{"status": "delivered", "recipient_id": "573001234567", "id": "wamid.abc"}],
                },
            }],
        }],
    }
    resp = client.post(
        "/v1/agents/whatsapp-test/channels/whatsapp/webhook",
        json=payload,
        headers={"X-Hub-Signature-256": "sha256=bypass"},
    )
    assert resp.status_code == 200
    status_value = {"statuses": [{"status": "delivered", "recipient_id": "573001234567", "id": "wamid.abc"}]}
    mock_dispatch.assert_called_once_with("statuses", status_value, "whatsapp-test")

# Test: unknown field dispatched to dispatcher
@pytest.mark.asyncio
async def test_unknown_field_dispatched(client, runtime_with_whatsapp_agent, mocker):
    mock_dispatch = mocker.patch(
        "astromesh.api.routes.agent_channels.webhook_dispatcher.dispatch",
        new_callable=AsyncMock,
    )
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "account_update", "value": {"event": "VERIFIED_ACCOUNT"}}]}],
    }
    resp = client.post(
        "/v1/agents/whatsapp-test/channels/whatsapp/webhook",
        json=payload,
        headers={"X-Hub-Signature-256": "sha256=bypass"},
    )
    assert resp.status_code == 200
    mock_dispatch.assert_called_once_with("account_update", {"event": "VERIFIED_ACCOUNT"}, "whatsapp-test")
```

- [ ] **Step 2: Run to confirm failures**

```bash
uv run pytest tests/test_agent_channels.py -v -k "contact_name or status_update or unknown_field"
```

Expected: FAIL

- [ ] **Step 3: Update `parse_incoming` to accept `value` dict**

`WhatsAppClient.parse_incoming` currently traverses the full payload (`entry[].changes[].value`). The dispatcher already iterates entries/changes, so `parse_incoming` should accept the `change["value"]` dict directly:

```python
# astromesh/channels/whatsapp.py — before
async def parse_incoming(self, payload: dict) -> list[ChannelMessage]:
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):

# after
async def parse_incoming(self, value: dict) -> list[ChannelMessage]:
    """Parse a single change value dict (change["value"]) into ChannelMessages.

    Args:
        value: The ``change["value"]`` dict from a Meta webhook entry.
               Contains ``messages``, ``contacts``, ``statuses``, etc.
    """
    messages: list[ChannelMessage] = []
    for msg in value.get("messages", []):
        msg_type = msg.get("type", "")
        # ... rest of parsing logic unchanged ...
```

Also update the ABC signature in `astromesh/channels/base.py`:
```python
# before
@abstractmethod
async def parse_incoming(self, payload: dict) -> list[ChannelMessage]: ...

# after
@abstractmethod
async def parse_incoming(self, value: dict) -> list[ChannelMessage]:
    """Parse a single change value dict into ChannelMessages."""
    ...
```

Update existing tests in `tests/test_whatsapp.py` that call `parse_incoming` with the full payload — replace them to call with `value` dict only (the `change["value"]` portion).

- [ ] **Step 4: Refactor the POST endpoint**

Replace the current `receive_agent_message` body in `astromesh/api/routes/agent_channels.py`:

```python
from astromesh.channels.webhook_dispatcher import webhook_dispatcher

@router.post("/agents/{agent_name}/channels/{channel_type}/webhook")
async def receive_agent_message(
    agent_name: str,
    channel_type: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Two-phase webhook dispatcher for per-agent channels.

    Phase 1 — signature validation (unchanged).
    Phase 2 — field-based dispatch:
      - field="messages" + has "messages" key → parse_incoming + _process_agent_message
      - field="messages" + has "statuses" key → StatusUpdateHandler (log + SSE)
      - any other field                        → WebhookEventDispatcher (log + SSE)
    """
    adapter, _ = get_agent_channel(_runtime, agent_name, channel_type)
    if adapter is None:
        return Response(status_code=404,
                        content=f"Agent '{agent_name}' has no {channel_type} channel")

    raw_body = await request.body()
    payload = await request.json()

    # Signature validation
    if channel_type == "whatsapp":
        sig = request.headers.get("X-Hub-Signature-256", "")
        if not adapter.verify_request(raw_body, sig):
            return Response(status_code=403, content="Invalid signature")

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            field = change.get("field", "")
            value = change.get("value", {})

            if field == "messages":
                # Build contact name lookup: {wa_id: display_name}
                contact_names: dict[str, str] = {
                    c["wa_id"]: c.get("profile", {}).get("name", "")
                    for c in value.get("contacts", [])
                    if "wa_id" in c
                }

                if "messages" in value:
                    messages = await adapter.parse_incoming(value)  # value = change["value"]
                    for msg in messages:
                        msg.contact_name = contact_names.get(msg.sender_id) or None
                        channel_event_bus.emit(ChannelEvent.create(
                            agent=agent_name,
                            channel=channel_type,
                            direction="in",
                            sender=msg.sender_id,
                            text=msg.text,
                            media=[{"type": m.media_type, "mime": m.mime_type}
                                   for m in msg.media] if msg.media else None,
                        ))
                        background_tasks.add_task(
                            _process_agent_message, agent_name, channel_type, msg
                        )

                if "statuses" in value:
                    await webhook_dispatcher.dispatch("statuses", value, agent_name)

            else:
                await webhook_dispatcher.dispatch(field, value, agent_name)

    return {"status": "ok"}
```

- [ ] **Step 5: Update `_process_agent_message` to use `context`**

```python
async def _process_agent_message(agent_name: str, channel_type: str, message) -> None:
    adapter = None
    try:
        adapter, _ = get_agent_channel(_runtime, agent_name, channel_type)
        if not adapter:
            return
        query = await build_multimodal_query(message, adapter)
        context = {"contact_name": message.contact_name} if message.contact_name else None
        result = await _runtime.run(
            agent_name=agent_name,
            query=query,
            session_id=f"{channel_type}_{message.sender_id}",
            context=context,   # uses existing engine.py:273 context param
        )
        answer = result.get("answer", "Sorry, I couldn't process your message.")
        await adapter.send_text(message.sender_id, answer)
        channel_event_bus.emit(ChannelEvent.create(
            agent=agent_name, channel=channel_type, direction="out",
            sender=message.sender_id, text=answer,
        ))
    except Exception:
        logger.exception("Error processing message from %s", message.sender_id)
        if adapter is not None:
            try:
                await adapter.send_text(message.sender_id, "Sorry, an error occurred.")
            except Exception:
                logger.exception("Failed to send error reply")
```

No changes needed in `engine.py` — `context` is already forwarded to `agent.run()`.

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_agent_channels.py tests/test_webhook_dispatcher.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add astromesh/channels/base.py astromesh/channels/whatsapp.py astromesh/api/routes/agent_channels.py tests/test_agent_channels.py tests/test_whatsapp.py
git commit -m "feat(webhook): two-phase dispatcher with contact name enrichment and context passthrough"
```

---

### Task 4: Developer documentation

**Files:**
- Create: `docs-site/src/content/docs/advanced/webhook-events.md`
- Modify: `docs-site/src/content/docs/advanced/whatsapp.md` (add cross-link)

- [ ] **Step 1: Create `webhook-events.md`**

```markdown
---
title: Webhook Event Dispatcher
description: How Astromesh classifies and routes incoming Meta webhook events — user messages vs. status updates vs. system events.
---

# Webhook Event Dispatcher

When Meta delivers a webhook POST to your agent's endpoint, the payload can
contain many different types of events — user messages, delivery receipts,
account updates, template status changes, and more.  Astromesh automatically
classifies each event so only genuine user messages reach your agent, while
other events are logged and surfaced in the Channel Activity panel.

## How it works

Every Meta webhook payload wraps events in a `change["field"]` key that
identifies the event category.  Astromesh inspects this field before any
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
3. Emits an `in` SSE event (visible in Channel Activity)
4. Runs `_process_agent_message()` in the background, which:
   - Builds the multimodal query
   - Calls `runtime.run()` with `session_id="whatsapp_{sender_phone}"` and `metadata={"contact_name": "..."}`
   - Sends the agent's reply back to WhatsApp
   - Emits an `out` SSE event

### Contact name in sessions

The agent session carries the contact's WhatsApp display name in metadata.
You can use it in your system prompt for personalized greetings:

```yaml
prompts:
  system: |
    You are a helpful assistant.
    {% if contact_name %}Address the user as {{ contact_name }}.{% endif %}
```

> **Note:** Contact name availability depends on the user's WhatsApp privacy
> settings. Always handle the case where it is absent.

### Status updates (delivery receipts)

When `value["statuses"]` is present, the built-in `StatusUpdateHandler` runs.
It logs each status and emits a `system` SSE event — **no message is sent to
the agent**.  Status types: `sent`, `delivered`, `read`, `failed`.

### System events (all other fields)

Any `change["field"]` other than `"messages"` (e.g. `account_update`,
`message_template_status_update`, `flows`) is routed to
`WebhookEventDispatcher`.  If no handler is registered for that field, the
`DefaultWebhookEventHandler` runs: it logs the event and emits a `system`
SSE event.

## Registering a custom handler

To react to a specific Meta webhook field, implement the
`WebhookEventHandler` protocol and register it at startup:

```python
# astromesh/channels/webhook_dispatcher.py — module-level singleton
from astromesh.channels.webhook_dispatcher import webhook_dispatcher

class TemplateStatusHandler:
    async def handle(self, field: str, value: dict, agent_name: str) -> None:
        # value contains the template status update payload
        template_name = value.get("message_template", {}).get("name", "")
        new_status = value.get("event", "")
        # ... your logic here

webhook_dispatcher.register("message_template_status_update", TemplateStatusHandler())
```

Register handlers at application startup, before the first webhook arrives.

## Meta webhook fields reference

The table below lists all Meta webhook fields and their default behavior in
Astromesh:

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
Astromesh Cortex with a distinct style (neither incoming nor outgoing).  This
lets you monitor delivery receipts, account events, and custom handler
activity without cluttering the conversation log.
```

- [ ] **Step 2: Add cross-link in `whatsapp.md`**

Find the "Webhook" section in `docs-site/src/content/docs/advanced/whatsapp.md` and add:

```markdown
> For details on how Astromesh classifies all incoming Meta webhook events
> (status updates, account events, template changes), see
> [Webhook Event Dispatcher](/advanced/webhook-events).
```

- [ ] **Step 3: Commit docs**

```bash
git add docs-site/src/content/docs/advanced/webhook-events.md docs-site/src/content/docs/advanced/whatsapp.md
git commit -m "docs: add Webhook Event Dispatcher reference page + cross-link from WhatsApp guide"
```

---

## Verification

1. **User message with contact name**: Send a WhatsApp message to the agent → `session.metadata["contact_name"]` is set; SSE `in` event appears in Channel Activity with sender name.
2. **Status update not routed to agent**: Trigger a delivery receipt → `StatusUpdateHandler` logs it; no agent run; `system` SSE event in Channel Activity.
3. **Unknown field dispatched**: Send a test payload with `field="account_update"` → `DefaultWebhookEventHandler` runs; `system` SSE event appears.
4. **Custom handler registration**: Register a handler for `"flows"` → that handler is called instead of the default.
5. **Backwards compatibility**: Existing `ChannelMessage` construction without `contact_name` still works (defaults to `None`).
