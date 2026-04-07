"""Resolve per-agent channel configuration into adapter instances."""

from __future__ import annotations

import logging
import os
import re

from astromesh.channels.whatsapp import WhatsAppClient

logger = logging.getLogger(__name__)

_ENV_PATTERN = re.compile(r"\$\{(\w+)\}")

# Cache: (agent_name, channel_type) -> adapter
_adapter_cache: dict[tuple[str, str], object] = {}


def resolve_env_vars(config: dict[str, str]) -> dict[str, str]:
    """Replace ${VAR} references in config values with environment variable values."""
    resolved = {}
    for key, value in config.items():
        if isinstance(value, str):
            resolved[key] = _ENV_PATTERN.sub(
                lambda m: os.environ.get(m.group(1), ""), value
            )
        else:
            resolved[key] = value
    return resolved


def get_channel_adapter(channel_spec: dict):
    """Create a channel adapter from a channel spec entry.

    channel_spec: {"type": "whatsapp", "config": {"access_token": "...", ...}}
    Returns configured adapter or None if type is unsupported.
    """
    channel_type = channel_spec.get("type", "")
    raw_config = channel_spec.get("config", {})
    config = resolve_env_vars(raw_config)

    if channel_type == "whatsapp":
        client = WhatsAppClient.__new__(WhatsAppClient)
        client.access_token = config.get("access_token", "")
        client.phone_number_id = config.get("phone_number_id", "")
        client.app_secret = config.get("app_secret", "")
        client.verify_token = config.get("verify_token", "")
        return client

    logger.warning("Unsupported channel type: %s", channel_type)
    return None


def get_agent_channel(runtime, agent_name: str, channel_type: str):
    """Get a configured channel adapter for a specific agent.

    Reads the agent's config from the runtime, finds the matching channel
    entry, and returns a configured adapter. Uses cache to avoid re-creating
    adapters on every webhook call.

    Returns (adapter, agent_config) tuple or (None, None) if not found.
    """
    cache_key = (agent_name, channel_type)
    if cache_key in _adapter_cache:
        return _adapter_cache[cache_key], runtime._agent_configs.get(agent_name)

    agent_config = runtime._agent_configs.get(agent_name)
    if not agent_config:
        return None, None

    channels = agent_config.get("spec", {}).get("channels", [])
    for ch in channels:
        if ch.get("type") == channel_type:
            adapter = get_channel_adapter(ch)
            if adapter:
                _adapter_cache[cache_key] = adapter
            return adapter, agent_config

    return None, None


def clear_cache():
    """Clear the adapter cache (useful when agent configs are reloaded)."""
    _adapter_cache.clear()
