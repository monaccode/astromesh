import pytest
import httpx
from unittest.mock import AsyncMock, patch
from astromesh_cloud.services.runtime_proxy import RuntimeProxy

_DUMMY_REQUEST = httpx.Request("POST", "http://test-runtime:8000/v1/agents/x/run")


def _make_response(status_code: int, json_body: dict, method: str = "POST", url: str = "http://test-runtime:8000/v1/agents/x/run") -> httpx.Response:
    resp = httpx.Response(status_code, json=json_body, request=httpx.Request(method, url))
    return resp


@pytest.fixture
def proxy():
    return RuntimeProxy(base_url="http://test-runtime:8000")

async def test_run_agent_namespaces_session(proxy):
    mock_response = _make_response(200, {"answer": "hello", "steps": [], "usage": None})
    with patch.object(proxy._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        result = await proxy.run_agent(runtime_name="acme--support", query="Hi", session_id="user-sess-1", org_slug="acme")
        call_kwargs = mock_post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["session_id"] == "acme:user-sess-1"
        assert result["answer"] == "hello"

async def test_run_agent_injects_byok_headers(proxy):
    mock_response = _make_response(200, {"answer": "ok", "steps": []})
    with patch.object(proxy._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        await proxy.run_agent(runtime_name="acme--bot", query="test", session_id="s1", org_slug="acme", provider_key="sk-test-123", provider_name="openai")
        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["X-Astromesh-Provider-Key"] == "sk-test-123"
        assert headers["X-Astromesh-Provider-Name"] == "openai"

async def test_health_returns_true_on_200(proxy):
    mock_response = _make_response(200, {"status": "ok"}, method="GET", url="http://test-runtime:8000/v1/health")
    with patch.object(proxy._client, "get", new_callable=AsyncMock, return_value=mock_response):
        assert await proxy.health() is True

async def test_health_returns_false_on_error(proxy):
    with patch.object(proxy._client, "get", new_callable=AsyncMock, side_effect=httpx.ConnectError("fail")):
        assert await proxy.health() is False
