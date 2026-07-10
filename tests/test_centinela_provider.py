from __future__ import annotations

import httpx
import respx

from astromesh.providers.centinela import SentimentResult, _CentinelaEndpointClient

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
        {"endpoint": "http://ep.test", "contract": CONTRACT, "invalid_policy": "retry", "max_retries": 2}
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
