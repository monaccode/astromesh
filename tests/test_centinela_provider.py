from __future__ import annotations

import httpx
import respx

from astromesh.providers.base import CompletionResponse
from astromesh.providers.centinela import (
    CentinelaProvider,
    SentimentResult,
    _CentinelaEndpointClient,
)

CONTRACT = {"labels": ["positivo", "neutral", "negativo"]}


def _chat_response(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


@respx.mock
async def test_classify_valid_label():
    respx.post("http://ep.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_chat_response("positivo"))
    )
    client = _CentinelaEndpointClient({"endpoint": "http://ep.test", "contract": CONTRACT})
    result = await client.classify("las ganancias del trimestre subieron")

    assert isinstance(result, SentimentResult)
    assert result.label == "positivo"
    assert result.valid is True
    assert result.score is None


@respx.mock
async def test_classify_out_of_set_is_invalid():
    respx.post("http://ep.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_chat_response("no tengo idea"))
    )
    client = _CentinelaEndpointClient({"endpoint": "http://ep.test", "contract": CONTRACT})
    result = await client.classify("texto ambiguo")

    assert result.label is None
    assert result.valid is False
    assert result.raw == "no tengo idea"


@respx.mock
async def test_classify_retry_policy_reclassifies():
    route = respx.post("http://ep.test/v1/chat/completions")
    route.side_effect = [
        httpx.Response(200, json=_chat_response("ninguna")),
        httpx.Response(200, json=_chat_response("negativo")),
    ]
    client = _CentinelaEndpointClient(
        {
            "endpoint": "http://ep.test",
            "contract": CONTRACT,
            "invalid_policy": "retry",
            "max_retries": 2,
        }
    )
    result = await client.classify("la deuda creció")

    assert result.label == "negativo"
    assert result.valid is True
    assert route.call_count == 2


@respx.mock
async def test_health_check_healthy_and_unhealthy():
    respx.get("http://ep.test/health").mock(return_value=httpx.Response(200))
    client = _CentinelaEndpointClient({"endpoint": "http://ep.test", "contract": CONTRACT})
    assert await client.health_check() is True

    respx.get("http://ep.test/health").mock(return_value=httpx.Response(503))
    assert await client.health_check() is False


@respx.mock
async def test_provider_complete_maps_label_to_content():
    respx.post("http://ep.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_chat_response("negativo"))
    )
    provider = CentinelaProvider(
        {"endpoint": "http://ep.test", "model": "centinela-sentiment", "contract": CONTRACT}
    )
    result = await provider.complete([{"role": "user", "content": "la empresa entró en default"}])

    assert isinstance(result, CompletionResponse)
    assert result.provider == "centinela"
    assert result.content == "negativo"
    assert result.model == "centinela-sentiment"
    assert result.metadata["label"] == "negativo"
    assert result.metadata["valid"] is True
    assert result.usage == {"input_tokens": 0, "output_tokens": 0}
    assert result.cost == 0.0


@respx.mock
async def test_provider_stream_yields_single_done_chunk():
    respx.post("http://ep.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_chat_response("neutral"))
    )
    provider = CentinelaProvider({"endpoint": "http://ep.test", "contract": CONTRACT})
    chunks = [c async for c in provider.stream([{"role": "user", "content": "sin cambios"}])]

    assert len(chunks) == 1
    assert chunks[0].content == "neutral"
    assert chunks[0].done is True
    assert chunks[0].provider == "centinela"


def test_provider_capabilities_and_cost():
    provider = CentinelaProvider({"endpoint": "http://ep.test", "contract": CONTRACT})
    assert provider.supports_tools() is False
    assert provider.supports_vision() is False
    assert provider.estimated_cost("centinela", 1000, 1000) == 0.0


@respx.mock
async def test_classify_sends_bearer_auth():
    route = respx.post("http://ep.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_chat_response("positivo")))
    client = _CentinelaEndpointClient(
        {"endpoint": "http://ep.test", "contract": CONTRACT, "api_key": "secret-token"})
    await client.classify("subieron las ganancias")
    assert route.calls.last.request.headers["authorization"] == "Bearer secret-token"


@respx.mock
async def test_api_key_env_is_read_from_environment(monkeypatch):
    monkeypatch.setenv("CENTINELA_TOKEN", "env-token")
    route = respx.post("http://ep.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_chat_response("neutral")))
    client = _CentinelaEndpointClient(
        {"endpoint": "http://ep.test", "contract": CONTRACT, "api_key_env": "CENTINELA_TOKEN"})
    await client.classify("informe estable")
    assert route.calls.last.request.headers["authorization"] == "Bearer env-token"


@respx.mock
async def test_endpoint_resolved_from_name_when_url_absent(monkeypatch):
    from astromesh.centinela import hf_endpoints
    monkeypatch.setattr(hf_endpoints, "resolve_url", lambda *a, **k: "http://resolved.test")
    respx.post("http://resolved.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_chat_response("positivo")))
    client = _CentinelaEndpointClient(
        {"endpoint_name": "centinela-sentiment-prod", "contract": CONTRACT})
    result = await client.classify("gran resultado")
    assert result.label == "positivo"
