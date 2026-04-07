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


from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from astromesh.api.routes.agent_channels import router, set_runtime


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
    from astromesh.channels.resolver import clear_cache

    app = FastAPI()
    app.include_router(router, prefix="/v1")
    set_runtime(mock_runtime)
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
