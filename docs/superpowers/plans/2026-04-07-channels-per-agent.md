# Channels per Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-agent webhook endpoints so each agent has its own `/v1/agents/{agent_name}/channels/{channel_type}/webhook` URL with its own credentials, replacing the global single-webhook design.

**Architecture:** New FastAPI router `agent_channels.py` with parameterized routes. A `resolve_channel_config()` helper reads the agent's YAML spec `channels:` section, resolves `${ENV_VAR}` references, and returns a configured adapter. The existing global webhook stays as deprecated fallback.

**Tech Stack:** Python 3.12, FastAPI, httpx, astromesh runtime

**Repo:** `D:/monaccode/astromesh`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `astromesh/channels/resolver.py` | Resolve agent channel config → adapter instance |
| Create | `astromesh/api/routes/agent_channels.py` | Per-agent webhook endpoints |
| Create | `tests/test_agent_channels.py` | Tests for new endpoints + resolver |
| Modify | `astromesh/api/main.py` | Register new router |

---

### Task 1: Channel config resolver

**Files:**
- Create: `astromesh/channels/resolver.py`
- Create: `tests/test_agent_channels.py` (partial — resolver tests)

- [ ] **Step 1: Write resolver tests**

Create `tests/test_agent_channels.py`:

```python
"""Tests for per-agent channel endpoints and resolver."""

from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock

from astromesh.channels.resolver import resolve_env_vars, get_channel_adapter


def test_resolve_env_vars_replaces_references(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "secret123")
    config = {"access_token": "${MY_TOKEN}", "static": "plain"}
    result = resolve_env_vars(config)
    assert result["access_token"] == "secret123"
    assert result["static"] == "plain"


def test_resolve_env_vars_missing_var_stays_empty():
    config = {"token": "${NONEXISTENT_VAR_XYZ}"}
    result = resolve_env_vars(config)
    assert result["token"] == ""


def test_get_channel_adapter_whatsapp(monkeypatch):
    monkeypatch.setenv("WA_TOKEN", "tok")
    monkeypatch.setenv("WA_PHONE", "123")
    monkeypatch.setenv("WA_SECRET", "sec")
    monkeypatch.setenv("WA_VERIFY", "ver")

    channel_spec = {
        "type": "whatsapp",
        "config": {
            "access_token": "${WA_TOKEN}",
            "phone_number_id": "${WA_PHONE}",
            "app_secret": "${WA_SECRET}",
            "verify_token": "${WA_VERIFY}",
        },
    }
    adapter = get_channel_adapter(channel_spec)
    assert adapter is not None
    assert adapter.access_token == "tok"
    assert adapter.phone_number_id == "123"
    assert adapter.verify_token == "ver"


def test_get_channel_adapter_unknown_type():
    adapter = get_channel_adapter({"type": "slack", "config": {}})
    assert adapter is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/monaccode/astromesh && python -m pytest tests/test_agent_channels.py -v -k "resolver or resolve or adapter"`
Expected: FAIL — module not found

- [ ] **Step 3: Create resolver**

Create `astromesh/channels/resolver.py`:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `cd D:/monaccode/astromesh && python -m pytest tests/test_agent_channels.py -v -k "resolver or resolve or adapter"`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd D:/monaccode/astromesh
git add astromesh/channels/resolver.py tests/test_agent_channels.py
git commit -m "feat(channels): add per-agent channel config resolver

resolve_env_vars replaces \${VAR} in config values.
get_channel_adapter creates adapter from channel spec.
get_agent_channel reads agent config and returns cached adapter."
```

---

### Task 2: Per-agent webhook route

**Files:**
- Create: `astromesh/api/routes/agent_channels.py`
- Modify: `tests/test_agent_channels.py` (add route tests)

- [ ] **Step 1: Write route tests**

Add to `tests/test_agent_channels.py`:

```python
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from astromesh.api.routes.agent_channels import router, set_runtime
import astromesh.api.routes.agent_channels as agent_channels_mod


@pytest.fixture
def mock_runtime():
    rt = MagicMock()
    rt._agent_configs = {
        "test-agent": {
            "spec": {
                "channels": [
                    {
                        "type": "whatsapp",
                        "config": {
                            "access_token": "test-token",
                            "phone_number_id": "12345",
                            "app_secret": "",
                            "verify_token": "my-verify",
                        },
                    }
                ]
            }
        }
    }
    rt.run = AsyncMock(return_value={"answer": "Hello!"})
    return rt


@pytest.fixture
def client(mock_runtime):
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/v1")
    set_runtime(mock_runtime)
    # Clear adapter cache between tests
    from astromesh.channels.resolver import clear_cache
    clear_cache()
    return TestClient(app)


def test_webhook_verify(client):
    resp = client.get(
        "/v1/agents/test-agent/channels/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "my-verify",
            "hub.challenge": "challenge123",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "challenge123"


def test_webhook_verify_wrong_token(client):
    resp = client.get(
        "/v1/agents/test-agent/channels/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "challenge123",
        },
    )
    assert resp.status_code == 403


def test_webhook_verify_unknown_agent(client):
    resp = client.get(
        "/v1/agents/nonexistent/channels/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "my-verify",
            "hub.challenge": "challenge123",
        },
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Create the route**

Create `astromesh/api/routes/agent_channels.py`:

```python
"""Per-agent channel webhook endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response

from astromesh.channels.media import build_multimodal_query
from astromesh.channels.resolver import get_agent_channel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["channels"])

_runtime = None


def set_runtime(runtime):
    global _runtime
    _runtime = runtime


@router.get("/agents/{agent_name}/channels/{channel_type}/webhook")
async def verify_agent_webhook(
    agent_name: str,
    channel_type: str,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Webhook verification for a specific agent's channel."""
    adapter, _ = get_agent_channel(_runtime, agent_name, channel_type)
    if adapter is None:
        return Response(status_code=404, content=f"Agent '{agent_name}' has no {channel_type} channel configured")

    if channel_type == "whatsapp":
        result = adapter.verify_webhook(hub_mode or "", hub_token or "", hub_challenge or "")
        if result is not None:
            return Response(content=result, media_type="text/plain")
    return Response(status_code=403)


async def _process_agent_message(agent_name: str, channel_type: str, message):
    """Process incoming message for a specific agent in background."""
    try:
        adapter, _ = get_agent_channel(_runtime, agent_name, channel_type)
        if not adapter:
            logger.error("No adapter for %s/%s during message processing", agent_name, channel_type)
            return

        query = await build_multimodal_query(message, adapter)
        result = await _runtime.run(
            agent_name=agent_name,
            query=query,
            session_id=f"{channel_type}_{message.sender_id}",
        )
        answer = result.get("answer", "Sorry, I couldn't process your message.")
        await adapter.send_text(message.sender_id, answer)
    except Exception:
        logger.exception("Failed to process %s message for agent %s from %s", channel_type, agent_name, message.sender_id)
        try:
            await adapter.send_text(message.sender_id, "Sorry, an error occurred. Please try again.")
        except Exception:
            logger.exception("Failed to send error reply to %s", message.sender_id)


@router.post("/agents/{agent_name}/channels/{channel_type}/webhook")
async def receive_agent_message(
    agent_name: str,
    channel_type: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Receive incoming messages for a specific agent's channel."""
    adapter, _ = get_agent_channel(_runtime, agent_name, channel_type)
    if adapter is None:
        return Response(status_code=404, content=f"Agent '{agent_name}' has no {channel_type} channel configured")

    body = await request.body()

    # Signature verification
    if channel_type == "whatsapp":
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not adapter.verify_request(body, signature):
            return Response(status_code=403)

    payload = await request.json()
    messages = await adapter.parse_incoming(payload)

    for msg in messages:
        logger.info("%s message for agent %s from %s: %s", channel_type, agent_name, msg.sender_id, msg.message_id)
        background_tasks.add_task(_process_agent_message, agent_name, channel_type, msg)

    return {"status": "ok"}
```

- [ ] **Step 3: Run tests**

Run: `cd D:/monaccode/astromesh && python -m pytest tests/test_agent_channels.py -v`
Expected: PASS (7 tests)

- [ ] **Step 4: Commit**

```bash
cd D:/monaccode/astromesh
git add astromesh/api/routes/agent_channels.py tests/test_agent_channels.py
git commit -m "feat(channels): add per-agent webhook endpoints

GET/POST /v1/agents/{agent_name}/channels/{channel_type}/webhook
Each agent gets its own webhook URL with its own credentials."
```

---

### Task 3: Register route in main.py

**Files:**
- Modify: `astromesh/api/main.py`

- [ ] **Step 1: Add import and registration**

In `astromesh/api/main.py`, add alongside the existing whatsapp import (around line 44):

```python
from astromesh.api.routes import agent_channels as agent_channels_route
```

Add `set_runtime` call alongside the existing ones (around line 55):

```python
agent_channels_route.set_runtime(r)
```

Register the router alongside existing routers (around line 109):

```python
app.include_router(agent_channels_route.router, prefix="/v1")
```

Do the same in the other lifespan branch where runtime is created fresh (look for where `whatsapp_route.set_runtime(runtime)` is called and add `agent_channels_route.set_runtime(runtime)` next to it).

- [ ] **Step 2: Run existing tests**

Run: `cd D:/monaccode/astromesh && python -m pytest tests/ -v -k "not orbit_gcp and not test_parse_compute_specs" --timeout=30`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd D:/monaccode/astromesh
git add astromesh/api/main.py
git commit -m "feat(channels): register per-agent channel routes in API

New endpoints available at /v1/agents/{name}/channels/{type}/webhook
alongside existing deprecated global /v1/channels/whatsapp/webhook."
```
