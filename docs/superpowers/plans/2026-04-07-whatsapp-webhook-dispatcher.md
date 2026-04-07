# WhatsApp Webhook Dispatcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-path webhook receiver with a two-phase dispatcher that classifies every Meta webhook event by `change["field"]`, routes user messages to the agent (enriched with contact display name), and forwards everything else through a `WebhookEventHandler` protocol.

**Architecture:** The POST endpoint iterates `entry[].changes[]` and inspects `change["field"]` before any parsing. Field `"messages"` with a `messages` key → existing pipeline (enriched). Field `"messages"` with a `statuses` key → `StatusUpdateHandler`. Any other field → `WebhookEventDispatcher` singleton. `parse_incoming` is updated to accept `change["value"]` directly instead of the full payload.

**Tech Stack:** Python 3.12, FastAPI, pytest-asyncio, existing `ChannelEventBus`, `ChannelMessage` dataclass.

---

## File Map

| Action | Path |
|--------|------|
| Modify | `astromesh/channels/base.py` |
| Modify | `astromesh/channels/event_bus.py` |
| Modify | `astromesh/channels/whatsapp.py` |
| Create | `astromesh/channels/webhook_dispatcher.py` |
| Modify | `astromesh/api/routes/agent_channels.py` |
| Modify | `tests/test_whatsapp.py` |
| Modify | `tests/test_agent_channels.py` |
| Create | `tests/test_webhook_dispatcher.py` |
| Create | `docs-site/src/content/docs/advanced/webhook-events.md` |
| Modify | `docs-site/src/content/docs/advanced/whatsapp.md` |

---

## Task 1: Add `contact_name` to `ChannelMessage` and `"system"` to `ChannelEvent`

**Files:**
- Modify: `astromesh/channels/base.py`
- Modify: `astromesh/channels/event_bus.py`
- Create: `tests/test_webhook_dispatcher.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_webhook_dispatcher.py`:

```python
"""Tests for the webhook event dispatcher and contact name enrichment."""
from __future__ import annotations

from astromesh.channels.base import ChannelMessage


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

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd D:/monaccode/astromesh
uv run pytest tests/test_webhook_dispatcher.py -v
```

Expected: `TypeError` — `ChannelMessage.__init__() got an unexpected keyword argument 'contact_name'`

- [ ] **Step 3: Add `contact_name` to `ChannelMessage`**

In `astromesh/channels/base.py`, add the field with a default so existing callsites don't break:

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
    contact_name: str | None = None  # populated from Meta contacts[] array
```

- [ ] **Step 4: Add `"system"` to `ChannelEvent.direction`**

In `astromesh/channels/event_bus.py`, find the `direction` field in `ChannelEvent` and update the Literal:

```python
# before
direction: Literal["in", "out"]

# after
direction: Literal["in", "out", "system"]
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_webhook_dispatcher.py -v
```

Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add astromesh/channels/base.py astromesh/channels/event_bus.py tests/test_webhook_dispatcher.py
git commit -m "feat(channels): add contact_name to ChannelMessage + system direction to ChannelEvent"
```

---

## Task 2: Create `WebhookEventDispatcher`

**Files:**
- Create: `astromesh/channels/webhook_dispatcher.py`
- Modify: `tests/test_webhook_dispatcher.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_webhook_dispatcher.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch

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
async def test_status_update_handler_emits_system_event(mocker):
    mock_emit = mocker.patch(
        "astromesh.channels.webhook_dispatcher.channel_event_bus.emit"
    )
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
    mock_emit = mocker.patch(
        "astromesh.channels.webhook_dispatcher.channel_event_bus.emit"
    )
    handler = DefaultWebhookEventHandler()
    await handler.handle("account_update", {}, "my-agent")
    mock_emit.assert_called_once()
    event = mock_emit.call_args[0][0]
    assert event.direction == "system"
    assert "account_update" in event.text


@pytest.mark.asyncio
async def test_dispatcher_has_status_handler_preregistered():
    dispatcher = WebhookEventDispatcher()
    assert "statuses" in dispatcher._handlers
    assert isinstance(dispatcher._handlers["statuses"], StatusUpdateHandler)
```

- [ ] **Step 2: Run to confirm failures**

```bash
uv run pytest tests/test_webhook_dispatcher.py -v
```

Expected: `ModuleNotFoundError: No module named 'astromesh.channels.webhook_dispatcher'`

- [ ] **Step 3: Create `webhook_dispatcher.py`**

Create `astromesh/channels/webhook_dispatcher.py`:

```python
"""Webhook event dispatcher for per-agent channel webhooks.

Classifies incoming Meta webhook payloads by ``change["field"]`` and routes
them to the appropriate handler.  User messages (``field="messages"``) go
through the existing ``parse_incoming`` pipeline.  Everything else is
dispatched here — either to a registered custom handler or to the built-in
default (log + SSE system event).

Adding a handler for a new Meta webhook field::

    from astromesh.channels.webhook_dispatcher import webhook_dispatcher

    class MyHandler:
        async def handle(self, field: str, value: dict, agent_name: str) -> None:
            ...  # your logic

    webhook_dispatcher.register("message_template_status_update", MyHandler())

Register handlers at application startup, before the first webhook arrives.
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
            field: The Meta webhook ``change["field"]`` value.
            value: The raw ``change["value"]`` dict from the Meta payload.
            agent_name: Name of the agent that owns this webhook.
        """
        ...


class DefaultWebhookEventHandler:
    """Fallback handler: logs the event and emits a ``system`` SSE event.

    Used for any ``change["field"]`` with no registered handler.
    Makes unhandled events visible in the ChannelActivityPanel without
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
    per status update.  Does NOT route anything to the agent.

    Status types emitted by Meta: ``sent``, ``delivered``, ``read``, ``failed``.
    """

    async def handle(self, field: str, value: dict, agent_name: str) -> None:
        for status in value.get("statuses", []):
            status_type = status.get("status", "unknown")
            recipient = status.get("recipient_id", "unknown")
            msg_id = status.get("id", "")
            logger.info(
                "message_status_update status=%s recipient=%s msg_id=%s agent=%s",
                status_type,
                recipient,
                msg_id,
                agent_name,
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

    Ships with ``StatusUpdateHandler`` pre-registered for ``"statuses"``
    (delivery/read receipts) and falls back to ``DefaultWebhookEventHandler``
    for any unregistered field.

    Example::

        dispatcher = WebhookEventDispatcher()
        dispatcher.register("flows", MyFlowsHandler())
        await dispatcher.dispatch("flows", value, agent_name)
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
# Import directly: ``from astromesh.channels.webhook_dispatcher import webhook_dispatcher``
webhook_dispatcher = WebhookEventDispatcher()
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_webhook_dispatcher.py -v
```

Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add astromesh/channels/webhook_dispatcher.py tests/test_webhook_dispatcher.py
git commit -m "feat(channels): add WebhookEventDispatcher with StatusUpdateHandler and DefaultWebhookEventHandler"
```

---

## Task 3: Update `parse_incoming` to accept `value` dict

**Files:**
- Modify: `astromesh/channels/base.py` (ABC signature)
- Modify: `astromesh/channels/whatsapp.py` (implementation)
- Modify: `tests/test_whatsapp.py` (update callers)

The current `parse_incoming` iterates the full Meta payload (`entry[].changes[].value`). Since the dispatcher already iterates entries and changes, `parse_incoming` should accept `change["value"]` directly — a simpler, more focused interface.

- [ ] **Step 1: Write a failing test for the new signature**

Append to `tests/test_webhook_dispatcher.py`:

```python
import pytest
from astromesh.channels.whatsapp import WhatsAppClient


@pytest.mark.asyncio
async def test_parse_incoming_accepts_value_dict():
    """parse_incoming receives change["value"], not the full payload."""
    client = WhatsAppClient()
    value = {
        "messaging_product": "whatsapp",
        "messages": [{
            "from": "573001234567",
            "id": "wamid.test1",
            "timestamp": "1712500000",
            "type": "text",
            "text": {"body": "hola"},
        }],
    }
    messages = await client.parse_incoming(value)
    assert len(messages) == 1
    assert messages[0].sender_id == "573001234567"
    assert messages[0].text == "hola"


@pytest.mark.asyncio
async def test_parse_incoming_empty_value():
    client = WhatsAppClient()
    assert await client.parse_incoming({}) == []
    assert await client.parse_incoming({"messages": []}) == []
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_webhook_dispatcher.py::test_parse_incoming_accepts_value_dict -v
```

Expected: FAIL — the current `parse_incoming` looks for `entry[]`, not `messages[]` at the top level, so it returns `[]` instead of the expected 1 message.

- [ ] **Step 3: Update `parse_incoming` in `whatsapp.py`**

Replace the full method body (currently lines 44–86 of `astromesh/channels/whatsapp.py`):

```python
async def parse_incoming(self, value: dict) -> list[ChannelMessage]:
    """Parse a single ``change["value"]`` dict into ChannelMessages.

    Args:
        value: The ``change["value"]`` dict from a Meta webhook entry.
               Contains ``messages``, ``contacts``, ``statuses``, etc.
               The caller (webhook endpoint) is responsible for iterating
               ``entry[].changes[]`` and passing each value here.

    Returns:
        List of parsed ChannelMessage objects (text and/or media).
        Unsupported message types (sticker, reaction, etc.) are silently skipped.
    """
    messages: list[ChannelMessage] = []
    for msg in value.get("messages", []):
        msg_type = msg.get("type", "")
        text: str | None = None
        media: list[MediaAttachment] = []

        if msg_type == "text":
            text = msg["text"]["body"]
        elif msg_type in _WA_MEDIA_TYPES:
            media_data = msg.get(msg_type, {})
            media.append(
                MediaAttachment(
                    media_type=_WA_MEDIA_TYPES[msg_type],
                    mime_type=media_data.get("mime_type", f"{msg_type}/*"),
                    content=None,
                    source_id=media_data.get("id", ""),
                    filename=media_data.get("filename"),
                )
            )
            caption = media_data.get("caption")
            if caption:
                text = caption
        else:
            continue  # Skip unsupported types (sticker, reaction, interactive, etc.)

        messages.append(
            ChannelMessage(
                sender_id=msg["from"],
                text=text,
                media=media,
                message_id=msg["id"],
                timestamp=msg.get("timestamp", ""),
                channel="whatsapp",
                raw_payload=msg,
            )
        )
    return messages
```

- [ ] **Step 4: Update ABC signature in `base.py`**

In `astromesh/channels/base.py`, update the abstract method:

```python
@abstractmethod
async def parse_incoming(self, value: dict) -> list[ChannelMessage]:
    """Parse a single change value dict (``change["value"]``) into ChannelMessages."""
    ...
```

- [ ] **Step 5: Update existing `test_whatsapp.py` callers**

All existing calls to `parse_incoming` pass the full payload. Update them to pass only the `change["value"]` portion. Find every call in `tests/test_whatsapp.py` and replace:

```python
# BEFORE — full payload
payload = {
    "entry": [{"changes": [{"value": {"messages": [...]}}]}],
}
messages = await client.parse_incoming(payload)

# AFTER — value dict only (the change["value"])
value = {"messages": [...]}
messages = await client.parse_incoming(value)
```

Specific tests to update (check for `"entry"` key in test payloads):
- `test_parse_incoming_text_message` — extract inner `value`
- `test_parse_incoming_image_message` — extract inner `value`
- `test_parse_incoming_audio_message` — extract inner `value`
- `test_parse_incoming_document_message` — extract inner `value`
- `test_parse_incoming_ignores_unsupported_types` — extract inner `value`
- `test_parse_incoming_empty_payload` — change `{}` and `{"entry": []}` to `{}` and `{"messages": []}`
- `test_parse_incoming_multiple_messages` — extract inner `value`

Example update for `test_parse_incoming_text_message`:
```python
# before
async def test_parse_incoming_text_message(self):
    client = WhatsAppClient()
    payload = {
        "entry": [{"changes": [{"value": {"messages": [{
            "from": "5511999999999",
            "id": "wamid.abc123",
            "timestamp": "1700000000",
            "type": "text",
            "text": {"body": "Hello"},
        }]}}]}],
    }
    messages = await client.parse_incoming(payload)

# after
async def test_parse_incoming_text_message(self):
    client = WhatsAppClient()
    value = {"messages": [{
        "from": "5511999999999",
        "id": "wamid.abc123",
        "timestamp": "1700000000",
        "type": "text",
        "text": {"body": "Hello"},
    }]}
    messages = await client.parse_incoming(value)
```

- [ ] **Step 6: Run all whatsapp tests**

```bash
uv run pytest tests/test_whatsapp.py tests/test_webhook_dispatcher.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add astromesh/channels/base.py astromesh/channels/whatsapp.py tests/test_whatsapp.py tests/test_webhook_dispatcher.py
git commit -m "refactor(channels): parse_incoming accepts change[value] dict directly instead of full payload"
```

---

## Task 4: Two-phase dispatch in the endpoint + contact name enrichment

**Files:**
- Modify: `astromesh/api/routes/agent_channels.py`
- Modify: `tests/test_agent_channels.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_agent_channels.py`. The existing `mock_runtime` and `client` fixtures use agent name `"test-agent"` — use that:

```python
from unittest.mock import AsyncMock, patch


def test_contact_name_extracted_and_set_on_message(client, mock_runtime, mocker):
    """Contact name from contacts[] is set on the ChannelMessage before processing."""
    captured_messages = []

    original_add_task = None

    def capture_task(func, *args, **kwargs):
        # args = (agent_name, channel_type, msg)
        if len(args) >= 3:
            captured_messages.append(args[2])  # the ChannelMessage

    mocker.patch(
        "astromesh.api.routes.agent_channels.BackgroundTasks.add_task",
        side_effect=capture_task,
    )

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
    resp = client.post(
        "/v1/agents/test-agent/channels/whatsapp/webhook",
        json=payload,
        headers={"X-Hub-Signature-256": "sha256=bypass"},
    )
    assert resp.status_code == 200
    assert len(captured_messages) == 1
    assert captured_messages[0].contact_name == "Juan Pérez"


def test_status_update_dispatched_not_sent_to_agent(client, mock_runtime, mocker):
    """Payloads with only statuses[] go to dispatcher, never to the agent."""
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
                    "statuses": [
                        {"status": "delivered", "recipient_id": "573001234567", "id": "wamid.abc"}
                    ],
                },
            }],
        }],
    }
    resp = client.post(
        "/v1/agents/test-agent/channels/whatsapp/webhook",
        json=payload,
        headers={"X-Hub-Signature-256": "sha256=bypass"},
    )
    assert resp.status_code == 200
    mock_runtime.run.assert_not_called()
    mock_dispatch.assert_called_once_with(
        "statuses",
        {"statuses": [{"status": "delivered", "recipient_id": "573001234567", "id": "wamid.abc"}]},
        "test-agent",
    )


def test_unknown_field_dispatched(client, mock_runtime, mocker):
    """Non-messages fields go to dispatcher."""
    mock_dispatch = mocker.patch(
        "astromesh.api.routes.agent_channels.webhook_dispatcher.dispatch",
        new_callable=AsyncMock,
    )
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "account_update", "value": {"event": "VERIFIED_ACCOUNT"}}]}],
    }
    resp = client.post(
        "/v1/agents/test-agent/channels/whatsapp/webhook",
        json=payload,
        headers={"X-Hub-Signature-256": "sha256=bypass"},
    )
    assert resp.status_code == 200
    mock_runtime.run.assert_not_called()
    mock_dispatch.assert_called_once_with(
        "account_update",
        {"event": "VERIFIED_ACCOUNT"},
        "test-agent",
    )
```

- [ ] **Step 2: Run to confirm failures**

```bash
uv run pytest tests/test_agent_channels.py -v -k "contact_name or status_update or unknown_field"
```

Expected: FAIL (3 failures)

- [ ] **Step 3: Refactor `receive_agent_message` in `agent_channels.py`**

Replace the entire `receive_agent_message` function body:

```python
from astromesh.channels.webhook_dispatcher import webhook_dispatcher

@router.post("/agents/{agent_name}/channels/{channel_type}/webhook")
async def receive_agent_message(
    agent_name: str,
    channel_type: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Two-phase webhook dispatcher for per-agent channel webhooks.

    Phase 1 — signature validation (unchanged for whatsapp).
    Phase 2 — field-based dispatch per ``change["field"]``:

    - ``field="messages"`` + ``"messages"`` key present → parse + enrich + agent
    - ``field="messages"`` + ``"statuses"`` key present → StatusUpdateHandler
    - any other field → WebhookEventDispatcher (log + SSE system event)

    The ``contacts`` array in the ``messages`` value is used to enrich each
    parsed message with the sender's WhatsApp display name before it is
    passed to ``_process_agent_message``.
    """
    adapter, _ = get_agent_channel(_runtime, agent_name, channel_type)
    if adapter is None:
        return Response(
            status_code=404,
            content=f"Agent '{agent_name}' has no {channel_type} channel configured",
        )

    raw_body = await request.body()
    payload = await request.json()

    # Phase 1: signature validation
    if channel_type == "whatsapp":
        sig = request.headers.get("X-Hub-Signature-256", "")
        if not adapter.verify_request(raw_body, sig):
            return Response(status_code=403, content="Invalid signature")

    # Phase 2: field-based dispatch
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
                    messages = await adapter.parse_incoming(value)
                    for msg in messages:
                        msg.contact_name = contact_names.get(msg.sender_id) or None
                        channel_event_bus.emit(
                            ChannelEvent.create(
                                agent=agent_name,
                                channel=channel_type,
                                direction="in",
                                sender=msg.sender_id,
                                text=msg.text,
                                media=(
                                    [{"type": m.media_type, "mime": m.mime_type} for m in msg.media]
                                    if msg.media
                                    else None
                                ),
                            )
                        )
                        background_tasks.add_task(
                            _process_agent_message, agent_name, channel_type, msg
                        )

                if "statuses" in value:
                    await webhook_dispatcher.dispatch("statuses", value, agent_name)

            else:
                await webhook_dispatcher.dispatch(field, value, agent_name)

    return {"status": "ok"}
```

- [ ] **Step 4: Update `_process_agent_message` to pass `context`**

Replace `_process_agent_message` in `astromesh/api/routes/agent_channels.py`:

```python
async def _process_agent_message(agent_name: str, channel_type: str, message) -> None:
    """Process incoming channel message in background, send reply, emit out-event."""
    adapter = None
    try:
        adapter, _ = get_agent_channel(_runtime, agent_name, channel_type)
        if not adapter:
            logger.error("No adapter for %s/%s during processing", agent_name, channel_type)
            return

        query = await build_multimodal_query(message, adapter)
        context = {"contact_name": message.contact_name} if message.contact_name else None
        result = await _runtime.run(
            agent_name=agent_name,
            query=query,
            session_id=f"{channel_type}_{message.sender_id}",
            context=context,
        )
        answer = result.get("answer", "Sorry, I couldn't process your message.")
        await adapter.send_text(message.sender_id, answer)

        channel_event_bus.emit(
            ChannelEvent.create(
                agent=agent_name,
                channel=channel_type,
                direction="out",
                sender=message.sender_id,
                text=answer,
            )
        )
    except Exception:
        logger.exception(
            "Error processing %s/%s message from %s",
            agent_name,
            channel_type,
            message.sender_id,
        )
        if adapter is not None:
            try:
                await adapter.send_text(message.sender_id, "Sorry, an error occurred.")
            except Exception:
                logger.exception("Failed to send error reply to %s", message.sender_id)
```

- [ ] **Step 5: Run all tests**

```bash
uv run pytest tests/test_agent_channels.py tests/test_webhook_dispatcher.py tests/test_whatsapp.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add astromesh/api/routes/agent_channels.py tests/test_agent_channels.py
git commit -m "feat(webhook): two-phase dispatcher with contact name enrichment and context passthrough"
```

---

## Task 5: Developer documentation

**Files:**
- Create: `docs-site/src/content/docs/advanced/webhook-events.md`
- Modify: `docs-site/src/content/docs/advanced/whatsapp.md`

- [ ] **Step 1: Create `webhook-events.md`**

Create `docs-site/src/content/docs/advanced/webhook-events.md` with this exact content:

```markdown
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
```

- [ ] **Step 2: Add cross-link in `whatsapp.md`**

Open `docs-site/src/content/docs/advanced/whatsapp.md`. Find the section that describes the webhook POST endpoint (search for "Webhook verification" or the POST handler description). Add this block immediately after that section heading:

```markdown
:::tip
For full details on how Astromesh classifies all incoming Meta webhook events
(status updates, account events, template changes, and how to register custom
handlers), see [Webhook Event Dispatcher](/advanced/webhook-events).
:::
```

- [ ] **Step 3: Commit docs**

```bash
git add docs-site/src/content/docs/advanced/webhook-events.md docs-site/src/content/docs/advanced/whatsapp.md
git commit -m "docs: add Webhook Event Dispatcher reference page + cross-link from WhatsApp guide"
```

---

## Verification

After all tasks complete, run the full test suite:

```bash
cd D:/monaccode/astromesh
uv run pytest tests/test_webhook_dispatcher.py tests/test_agent_channels.py tests/test_whatsapp.py -v
```

Expected: All tests pass.

Manual end-to-end checks:

1. **User message with contact name**: Send a WhatsApp message → `msg.contact_name` is set → agent runs → SSE `in`/`out` events in Channel Activity show sender name.
2. **Status update not routed to agent**: Trigger a delivery receipt (or send a test payload with `statuses[]`) → `StatusUpdateHandler` logs it → no `runtime.run()` call → `system` SSE event in Channel Activity.
3. **Unknown field dispatched**: POST a payload with `field="account_update"` → `DefaultWebhookEventHandler` logs it → `system` SSE event → no agent run.
4. **Custom handler registration**: Register a handler for `"flows"` via `webhook_dispatcher.register(...)` → that handler is called for `flows` payloads instead of the default.
5. **Backwards compat**: Existing code that constructs `ChannelMessage` without `contact_name` works unchanged (field defaults to `None`).
