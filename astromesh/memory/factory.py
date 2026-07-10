"""Factory mapping declarative memory config to conversation backends."""

from __future__ import annotations

from astromesh.core.memory import ConversationBackend

_DEFAULT_TTL = 259200  # 72h


def build_conversation_backend(conv_config: dict | None) -> ConversationBackend | None:
    """Build a ConversationBackend from a normalized conversational config.

    conv_config is memory_config["conversational"], e.g.
    {"backend": "redis", "connection": {"url": "redis://..."}, "ttl": 259200}.
    Returns None when no backend is declared.
    """
    if not conv_config:
        return None
    backend = conv_config.get("backend")
    if not backend:
        return None

    if backend == "redis":
        from astromesh.memory.backends.redis_conv import RedisConversationBackend

        url = conv_config["connection"]["url"]
        ttl = conv_config.get("ttl", _DEFAULT_TTL)
        return RedisConversationBackend(url, ttl=ttl)

    raise ValueError(f"unknown conversational backend {backend!r}")
