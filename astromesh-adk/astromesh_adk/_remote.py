"""Run an agent on a remote Astromesh node, by name.

With a connection in effect (``connect()``, ``remote()`` or ``agent.bind()``), ``run()`` and
``stream()`` call the node's ``/v1/agents/{name}/run`` and ``/v1/ws/agent/{name}`` instead of
the local runtime. The agent must already be deployed on the node under the same name: the
local definition is a handle, and its Python tools and handler do not travel.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from urllib.parse import urlencode

import httpx
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import InvalidStatus

from astromesh_adk.connection import RemoteConnection
from astromesh_adk.exceptions import AgentNotFoundError, RemoteError, RemoteUnavailableError
from astromesh_adk.result import RunResult, StreamEvent

TIMEOUT_SECONDS = 300.0


def _headers(conn: RemoteConnection) -> dict[str, str]:
    # The node itself doesn't authenticate; the hub (Nexus) or a gateway in front does, with
    # X-API-Key or a bearer token — send both when there is a key.
    if not conn.api_key:
        return {}
    return {"Authorization": f"Bearer {conn.api_key}", "X-API-Key": conn.api_key}


def _result(body: dict, latency_ms: float, url: str) -> RunResult:
    usage = body.get("usage") or {}
    by_model = usage.get("by_model") or []
    return RunResult(
        answer=body.get("answer", ""),
        steps=body.get("steps") or [],
        trace=body.get("trace"),
        cost=sum(m.get("cost", 0.0) or 0.0 for m in by_model),
        tokens={"input": usage.get("tokens_in", 0), "output": usage.get("tokens_out", 0)},
        latency_ms=latency_ms,
        model=usage.get("model", ""),
        metadata={
            "remote": url,
            "propuestas": body.get("propuestas") or [],
            "data": body.get("data"),
            "chain": body.get("chain"),
        },
    )


def _detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return response.text
    if isinstance(detail, dict):
        return detail.get("message") or json.dumps(detail)
    return str(detail)


async def run_remote(
    conn: RemoteConnection, agent_name: str, query: str, session_id: str, context: dict | None
) -> RunResult:
    url = f"{conn.url.rstrip('/')}/v1/agents/{agent_name}/run"
    payload = {"query": query, "session_id": session_id, "context": context}
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=_headers(conn))
    except httpx.TransportError as exc:
        raise RemoteUnavailableError(f"{conn.url} unreachable: {exc}") from exc
    if response.status_code == 404:
        raise AgentNotFoundError(f"agent '{agent_name}' is not deployed on {conn.url}")
    if response.status_code >= 400:
        raise RemoteError(f"{conn.url} answered {response.status_code}: {_detail(response)}")
    return _result(response.json(), (time.monotonic() - started) * 1000, conn.url)


async def stream_remote(
    conn: RemoteConnection, agent_name: str, query: str, session_id: str
) -> AsyncIterator[StreamEvent]:
    """Map the node's WS events: token → token, tool_call → step, done → done (with result).

    The WS protocol takes only the query — per-run `context` is not carried over it.
    """
    base = conn.url.rstrip("/").replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    url = f"{base}/v1/ws/agent/{agent_name}?{urlencode({'session_id': session_id})}"
    started = time.monotonic()
    try:
        async with ws_connect(url, additional_headers=_headers(conn)) as ws:
            await ws.send(json.dumps({"query": query}))
            async for raw in ws:
                event = json.loads(raw)
                kind = event.get("type")
                if kind == "token":
                    yield StreamEvent(type="token", content=event.get("content", ""))
                elif kind == "tool_call":
                    yield StreamEvent(type="step", step=event)
                elif kind == "error":
                    raise RemoteError(f"{conn.url}: {event.get('message', 'run failed')}")
                elif kind == "done":
                    latency = (time.monotonic() - started) * 1000
                    yield StreamEvent(type="done", result=_result(event, latency, conn.url))
                    return
    except InvalidStatus as exc:
        raise RemoteError(f"{conn.url} refused the stream: {exc}") from exc
    except OSError as exc:
        raise RemoteUnavailableError(f"{conn.url} unreachable: {exc}") from exc
