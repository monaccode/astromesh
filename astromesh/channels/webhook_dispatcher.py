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
