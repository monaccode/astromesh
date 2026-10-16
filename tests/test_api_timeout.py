from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from astromesh.api import ws
from astromesh.errors import AgentRunTimeout


async def test_run_timeout_devuelve_504(client, monkeypatch):
    from astromesh.api.routes import agents

    rt = MagicMock()
    rt.run = AsyncMock(side_effect=AgentRunTimeout("a", 60))
    rt.has_chain = lambda _: False
    monkeypatch.setattr(agents, "_runtime", rt)
    resp = await client.post("/v1/agents/a/run", json={"query": "q", "session_id": "s"})
    assert resp.status_code == 504
    assert resp.json()["detail"] == {"error": "timeout", "agent": "a", "timeout_seconds": 60}


def test_ws_timeout_manda_error_timeout():
    app = FastAPI()
    app.include_router(ws.router, prefix="/v1")
    rt = MagicMock()
    rt.run = AsyncMock(side_effect=AgentRunTimeout("a", 60))
    ws.set_runtime(rt)
    try:
        with TestClient(app).websocket_connect("/v1/ws/agent/a?session_id=s") as sock:
            sock.send_json({"query": "q"})
            sock.receive_json()  # status
            ev = sock.receive_json()
    finally:
        ws.set_runtime(None)
    assert (ev["type"], ev["error"]) == ("error", "timeout")
    assert (ev["agent"], ev["timeout_seconds"]) == ("a", 60)
