"""Tests for the HTTP client module."""

import os
from unittest.mock import MagicMock, patch

from astromesh_cli.client import (
    DEFAULT_URL,
    api_get,
    api_get_params,
    api_post,
    api_post_with_timeout,
    get_base_url,
)


def test_get_base_url_default():
    env = os.environ.copy()
    env.pop("ASTROMESH_DAEMON_URL", None)
    with patch.dict(os.environ, env, clear=True):
        assert get_base_url() == DEFAULT_URL


def test_get_base_url_from_env():
    with patch.dict(os.environ, {"ASTROMESH_DAEMON_URL": "http://myhost:9999"}):
        assert get_base_url() == "http://myhost:9999"


def test_api_get_returns_json():
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "ok"}
    mock_response.raise_for_status = MagicMock()
    with patch("astromesh_cli.client.httpx") as mock_httpx:
        mock_httpx.get.return_value = mock_response
        result = api_get("/v1/system/status")
        assert result == {"status": "ok"}
        mock_httpx.get.assert_called_once()
        call_args = mock_httpx.get.call_args
        assert call_args[0][0].endswith("/v1/system/status")


def test_api_post_sends_json():
    mock_response = MagicMock()
    mock_response.json.return_value = {"result": "done"}
    mock_response.raise_for_status = MagicMock()
    with patch("astromesh_cli.client.httpx") as mock_httpx:
        mock_httpx.post.return_value = mock_response
        result = api_post("/v1/agents/test/run", {"query": "hello"})
        assert result == {"result": "done"}
        mock_httpx.post.assert_called_once()
        call_kwargs = mock_httpx.post.call_args[1]
        assert call_kwargs["json"] == {"query": "hello"}


def test_api_post_with_timeout():
    mock_response = MagicMock()
    mock_response.json.return_value = {"result": "done"}
    mock_response.raise_for_status = MagicMock()
    with patch("astromesh_cli.client.httpx") as mock_httpx:
        mock_httpx.post.return_value = mock_response
        result = api_post_with_timeout("/v1/agents/test/run", {"query": "hello"}, timeout=60.0)
        assert result == {"result": "done"}
        call_kwargs = mock_httpx.post.call_args[1]
        assert call_kwargs["timeout"] == 60.0


def test_api_get_params():
    mock_response = MagicMock()
    mock_response.json.return_value = [{"id": "trace-1"}]
    mock_response.raise_for_status = MagicMock()
    with patch("astromesh_cli.client.httpx") as mock_httpx:
        mock_httpx.get.return_value = mock_response
        result = api_get_params("/v1/traces", params={"agent": "test"})
        assert result == [{"id": "trace-1"}]
        call_kwargs = mock_httpx.get.call_args[1]
        assert call_kwargs["params"] == {"agent": "test"}


def test_api_post_no_body():
    mock_response = MagicMock()
    mock_response.json.return_value = {}
    mock_response.raise_for_status = MagicMock()
    with patch("astromesh_cli.client.httpx") as mock_httpx:
        mock_httpx.post.return_value = mock_response
        result = api_post("/v1/some/path")
        assert result == {}
        call_kwargs = mock_httpx.post.call_args[1]
        assert call_kwargs["json"] is None
