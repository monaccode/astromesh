"""Tests for PeerClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astromesh.runtime.peers import PeerClient


@pytest.fixture
def peer_config():
    return [
        {"name": "inference-1", "url": "http://inference:8000", "services": ["inference"]},
        {
            "name": "worker-1",
            "url": "http://worker:8000",
            "services": ["agents", "tools", "memory"],
        },
        {"name": "worker-2", "url": "http://worker2:8000", "services": ["agents", "tools"]},
    ]


def test_find_peers(peer_config):
    client = PeerClient(peer_config)
    inference_peers = client.find_peers("inference")
    assert len(inference_peers) == 1
    assert inference_peers[0]["name"] == "inference-1"


def test_find_peers_multiple(peer_config):
    client = PeerClient(peer_config)
    agent_peers = client.find_peers("agents")
    assert len(agent_peers) == 2


def test_find_peers_none(peer_config):
    client = PeerClient(peer_config)
    assert client.find_peers("channels") == []


def test_peer_list(peer_config):
    client = PeerClient(peer_config)
    peers = client.list_peers()
    assert len(peers) == 3
    assert peers[0]["name"] == "inference-1"


async def test_health_check_success(peer_config):
    client = PeerClient(peer_config)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok"}
    with patch.object(client, "_http") as mock_http:
        mock_http.get = AsyncMock(return_value=mock_resp)
        result = await client.health_check("inference-1")
    assert result is True


async def test_health_check_failure(peer_config):
    client = PeerClient(peer_config)
    with patch.object(client, "_http") as mock_http:
        mock_http.get = AsyncMock(side_effect=Exception("Connection refused"))
        result = await client.health_check("inference-1")
    assert result is False


async def test_health_check_unknown_peer(peer_config):
    client = PeerClient(peer_config)
    result = await client.health_check("nonexistent")
    assert result is False


async def test_forward_request(peer_config):
    client = PeerClient(peer_config)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"answer": "hello"}
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client, "_http") as mock_http:
        mock_http.request = AsyncMock(return_value=mock_resp)
        result = await client.forward(
            "inference", "POST", "/v1/agents/test/run", json={"query": "hi"}
        )
    assert result == {"answer": "hello"}


async def test_forward_no_peer_raises(peer_config):
    client = PeerClient(peer_config)
    with pytest.raises(RuntimeError, match="No peer available"):
        await client.forward("channels", "GET", "/v1/channels")


def test_to_dict(peer_config):
    client = PeerClient(peer_config)
    d = client.to_dict()
    assert len(d) == 3
    assert d[0]["name"] == "inference-1"
    assert d[0]["url"] == "http://inference:8000"
    assert d[0]["services"] == ["inference"]
