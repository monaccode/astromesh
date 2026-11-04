"""Headers extra configurables en el provider OpenAI-compatible."""

import httpx
import pytest
import respx

from astromesh.errors import ModelProviderError
from astromesh.providers.openai_compat import OpenAICompatProvider
from astromesh.runtime.engine import build_candidate_provider

URL = "https://gateway.example/v1/chat/completions"
OK = {"choices": [{"message": {"role": "assistant", "content": "hi"}}], "usage": {}}
MESSAGES = [{"role": "user", "content": "hola"}]


def _config(**extra):
    return {"base_url": "https://gateway.example/v1", "api_key": "sk-test", **extra}


@respx.mock
async def test_custom_headers_sent(monkeypatch):
    monkeypatch.setenv("GATEWAY_KEY", "secret-from-env")
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=OK))
    provider = OpenAICompatProvider(
        _config(headers={"X-Gateway-Key": "${GATEWAY_KEY}", "X-Tenant-Id": "acme"})
    )
    await provider.complete(MESSAGES)

    sent = route.calls.last.request.headers
    assert sent["x-gateway-key"] == "secret-from-env"
    assert sent["x-tenant-id"] == "acme"
    assert sent["authorization"] == "Bearer sk-test"


@respx.mock
async def test_custom_headers_sent_on_stream():
    route = respx.post(URL).mock(return_value=httpx.Response(200, text="data: [DONE]\n\n"))
    provider = OpenAICompatProvider(_config(headers={"X-Tenant-Id": "acme"}))
    chunks = [c async for c in provider.stream(MESSAGES)]

    assert chunks[-1].done
    assert route.calls.last.request.headers["x-tenant-id"] == "acme"


@pytest.mark.parametrize("name", ["Authorization", "authorization", "AUTHORIZATION"])
def test_authorization_override_rejected(name):
    with pytest.raises(ModelProviderError) as exc:
        OpenAICompatProvider(_config(headers={name: "Bearer other"}))
    assert exc.value.code == "model_provider_invalid_headers"
    assert "other" not in str(exc.value)


def test_unset_variable_rejected_without_leaking(monkeypatch):
    monkeypatch.delenv("GATEWAY_KEY", raising=False)
    with pytest.raises(ModelProviderError) as exc:
        OpenAICompatProvider(_config(headers={"X-Gateway-Key": "${GATEWAY_KEY}"}))
    assert "X-Gateway-Key" in str(exc.value)


@respx.mock
async def test_headers_not_in_error_messages():
    respx.post(URL).mock(return_value=httpx.Response(400, json={"error": "bad field"}))
    provider = OpenAICompatProvider(_config(headers={"X-Gateway-Key": "super-secret-value"}))
    with pytest.raises(ModelProviderError) as exc:
        await provider.complete(MESSAGES)

    text = f"{exc.value} {exc.value.hint}"
    assert "bad field" in text
    assert "super-secret-value" not in text
    assert "X-Gateway-Key" not in text


def test_no_headers_is_the_default():
    assert OpenAICompatProvider(_config())._extra_headers == {}


def test_engine_block_forwards_headers():
    provider = build_candidate_provider(
        {
            "source": "openai_compat",
            "model": "gpt-4o",
            "endpoint": "https://gateway.example/v1",
            "headers": {"X-Tenant-Id": "acme"},
        }
    )
    assert provider._extra_headers == {"X-Tenant-Id": "acme"}
