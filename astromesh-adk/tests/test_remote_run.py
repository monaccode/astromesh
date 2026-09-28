"""Con una conexión remota, agent.run()/stream() corren el agente del mismo nombre en el nodo."""

import json

import httpx
import pytest
import respx

import astromesh_adk
from astromesh_adk import Agent, agent, connect, disconnect, remote
from astromesh_adk.exceptions import AgentNotFoundError, RemoteError, RemoteUnavailableError

NODE = "http://node.test:8000"
RESPONSE = {
    "answer": "hola",
    "steps": [{"action": "search"}],
    "usage": {
        "tokens_in": 12,
        "tokens_out": 3,
        "model": "gpt-4o",
        "by_model": [
            {
                "provider": "openai",
                "model": "gpt-4o",
                "role": "default",
                "calls": 1,
                "tokens_in": 12,
                "tokens_out": 3,
                "cost": 0.002,
            }
        ],
    },
    "trace": None,
    "data": None,
    "chain": None,
    "propuestas": [
        {
            "tool": "erp_crear",
            "tipo": "api",
            "destino": "erp",
            "operacion": "crear",
            "argumentos": {},
        }
    ],
}


@agent(name="support", model="openai/gpt-4o")
async def support(ctx):
    """Help the customer."""
    return


class Researcher(Agent):
    name = "researcher"
    model = "openai/gpt-4o"


@pytest.fixture(autouse=True)
def _no_global_connection():
    disconnect()
    yield
    disconnect()


@respx.mock
async def test_bound_agent_runs_on_the_node():
    route = respx.post(f"{NODE}/v1/agents/support/run").mock(
        return_value=httpx.Response(200, json=RESPONSE)
    )
    support.bind(NODE, api_key="k1")
    try:
        result = await support.run("hi", session_id="s1", context={"sender_phone": "1"})
    finally:
        support.bind(None, None)
    sent = json.loads(route.calls[0].request.content)
    assert sent == {"query": "hi", "session_id": "s1", "context": {"sender_phone": "1"}}
    headers = route.calls[0].request.headers
    assert headers["authorization"] == "Bearer k1" and headers["x-api-key"] == "k1"
    assert result.answer == "hola"
    assert result.tokens == {"input": 12, "output": 3}
    assert result.cost == pytest.approx(0.002)
    assert result.model == "gpt-4o"
    assert result.metadata["remote"] == NODE
    assert result.metadata["propuestas"][0]["tool"] == "erp_crear"


@respx.mock
async def test_global_connect_is_used():
    respx.post(f"{NODE}/v1/agents/support/run").mock(
        return_value=httpx.Response(200, json=RESPONSE)
    )
    connect(NODE, api_key="")
    result = await support.run("hi")
    assert result.answer == "hola"


@respx.mock
async def test_scoped_remote_wins_over_global_and_class_agents_work():
    respx.post(f"{NODE}/v1/agents/researcher/run").mock(
        return_value=httpx.Response(200, json=RESPONSE)
    )
    connect("http://other.test", api_key="x")
    async with remote(NODE, api_key="k"):
        result = await Researcher().run("hi")
    assert result.metadata["remote"] == NODE


def test_get_connection_falls_back_to_the_global_one():
    connect(NODE, api_key="k")
    assert astromesh_adk.connection.get_connection().url == NODE


@respx.mock
async def test_unknown_agent_on_the_node_is_agent_not_found():
    respx.post(f"{NODE}/v1/agents/support/run").mock(
        return_value=httpx.Response(404, json={"detail": "Agent 'support' not found"})
    )
    connect(NODE, api_key="k")
    with pytest.raises(AgentNotFoundError, match="support"):
        await support.run("hi")


@respx.mock
async def test_node_error_is_remote_error_with_the_detail():
    respx.post(f"{NODE}/v1/agents/support/run").mock(
        return_value=httpx.Response(502, json={"detail": {"message": "provider down"}})
    )
    connect(NODE, api_key="k")
    with pytest.raises(RemoteError, match="provider down"):
        await support.run("hi")


@respx.mock
async def test_unreachable_node_is_remote_unavailable():
    respx.post(f"{NODE}/v1/agents/support/run").mock(side_effect=httpx.ConnectError("refused"))
    connect(NODE, api_key="k")
    with pytest.raises(RemoteUnavailableError):
        await support.run("hi")


async def test_stream_maps_ws_events(monkeypatch):
    import astromesh_adk._remote as remote_mod

    frames = [
        {"type": "status", "status": "processing"},
        {"type": "token", "content": "thinking"},
        {"type": "tool_call", "id": "1", "name": "search", "arguments": {"q": "x"}},
        {"type": "tool_result", "id": "1", "ok": True},
        {"type": "done", "answer": "hola", "usage": RESPONSE["usage"], "propuestas": []},
    ]
    sent = {}

    class FakeWS:
        async def send(self, data):
            sent["msg"] = json.loads(data)

        def __aiter__(self):
            return self._gen()

        async def _gen(self):
            for f in frames:
                yield json.dumps(f)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    def fake_connect(url, additional_headers=None, **kw):
        sent["url"], sent["headers"] = url, additional_headers
        return FakeWS()

    monkeypatch.setattr(remote_mod, "ws_connect", fake_connect)
    connect(NODE, api_key="k")
    events = [e async for e in support.stream("hi", session_id="s 1")]
    assert sent["url"] == "ws://node.test:8000/v1/ws/agent/support?session_id=s+1"
    assert sent["msg"] == {"query": "hi"}
    assert [e.type for e in events] == ["token", "step", "done"]
    assert events[1].step["name"] == "search"
    assert events[-1].result.answer == "hola"


async def test_stream_error_frame_raises(monkeypatch):
    import astromesh_adk._remote as remote_mod

    class FakeWS:
        async def send(self, data):
            pass

        def __aiter__(self):
            async def g():
                yield json.dumps({"type": "error", "message": "boom"})

            return g()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(remote_mod, "ws_connect", lambda url, **kw: FakeWS())
    connect(NODE, api_key="k")
    with pytest.raises(RemoteError, match="boom"):
        _ = [e async for e in support.stream("hi")]
