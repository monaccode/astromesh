"""on_event: observing a run while it happens, at the engine level (no HTTP)."""

from __future__ import annotations

import pytest

from astromesh.runtime.engine import Agent, _emit


class FakeResponse:
    """Shaped like the providers' CompletionResponse, minus what the engine ignores."""

    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.model = "fake-model"
        self.provider = "fake"
        self.latency_ms = 1
        self.cost = 0.0
        self.usage = {"input_tokens": 1, "output_tokens": 1}


def test_emit_is_a_noop_without_a_callback():
    _emit(None, {"type": "token", "content": "hi"})  # must not raise


def test_emit_delivers_the_event():
    seen = []
    _emit(seen.append, {"type": "token", "content": "hi"})
    assert seen == [{"type": "token", "content": "hi"}]


def test_emit_swallows_a_raising_callback():
    def boom(_event):
        raise RuntimeError("observer is broken")

    # An observer must never be able to break the run it observes.
    _emit(boom, {"type": "token", "content": "hi"})


def test_emit_swallows_a_raising_callback_and_logs_it(caplog):
    def boom(_event):
        raise RuntimeError("observer is broken")

    with caplog.at_level("ERROR"):
        _emit(boom, {"type": "token", "content": "hi"})
    assert "on_event" in caplog.text


class RecordingPattern:
    """A pattern that drives model_fn/tool_fn the way the real ones do.

    Every real pattern receives exactly these two closures and calls
    `await tool_fn(name, args)` — so exercising them here exercises what all six
    patterns will do.
    """

    def __init__(self, script=None):
        self.script = script or []
        self.tool_ran_after = []

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        for item in self.script:
            if item[0] == "model":
                await model_fn([{"role": "user", "content": query}], tools)
            elif item[0] == "tool":
                await tool_fn(item[1], item[2])
        return {"answer": "done", "steps": []}


def _make_agent(pattern, tool_impl=None, model_content="thinking"):
    """Build an Agent with everything the run loop touches stubbed out."""
    from unittest.mock import AsyncMock, MagicMock

    agent = Agent.__new__(Agent)  # bypass __init__: we only exercise run()
    agent.name = "test-agent"
    agent._pattern = pattern
    agent._role_map = {}
    agent._orchestration_config = {"pattern": "recording"}
    agent._permissions = {}
    agent._guardrails = {}
    agent._rag = None
    agent._knowledge = None
    agent._system_prompt = "you are a test agent"

    router = MagicMock()
    router.route = AsyncMock(return_value=FakeResponse(content=model_content))
    agent._routers = {"default": router}

    tools = MagicMock()
    tools.execute = AsyncMock(side_effect=tool_impl or (lambda n, a, c: "observation"))
    tools.get_tool_schemas = MagicMock(return_value=[])
    agent._tools = tools

    memory = MagicMock()
    memory.build_context = AsyncMock(return_value="")
    memory.persist_turn = AsyncMock()
    agent._memory = memory

    prompt = MagicMock()
    prompt.render = MagicMock(return_value="you are a test agent")
    agent._prompt_engine = prompt

    return agent


async def test_tool_call_is_emitted_before_the_tool_runs():
    order = []

    async def tool_impl(name, args, ctx):
        order.append("tool-executed")
        return "observation"

    events = []

    def on_event(e):
        order.append(e["type"])
        events.append(e)

    agent = _make_agent(RecordingPattern([("tool", "search", {"q": "x"})]), tool_impl=tool_impl)
    await agent.run("hola", "s1", on_event=on_event)

    assert order == ["tool_call", "tool-executed", "tool_result"]
    assert events[0]["name"] == "search"
    assert events[0]["arguments"] == {"q": "x"}
    assert events[1]["ok"] is True


async def test_tool_call_and_tool_result_share_an_id():
    events = []
    agent = _make_agent(RecordingPattern([("tool", "search", {"q": "x"})]))
    await agent.run("hola", "s1", on_event=events.append)

    call = next(e for e in events if e["type"] == "tool_call")
    result = next(e for e in events if e["type"] == "tool_result")
    assert call["id"] == result["id"]
    assert call["id"]


async def test_ids_differ_across_calls():
    events = []
    agent = _make_agent(RecordingPattern([("tool", "a", {}), ("tool", "b", {})]))
    await agent.run("hola", "s1", on_event=events.append)

    ids = [e["id"] for e in events if e["type"] == "tool_call"]
    assert len(ids) == 2 and ids[0] != ids[1]


async def test_a_raising_tool_emits_ok_false_and_still_propagates():
    async def boom(name, args, ctx):
        raise RuntimeError("tool exploded")

    events = []
    agent = _make_agent(RecordingPattern([("tool", "search", {})]), tool_impl=boom)

    with pytest.raises(RuntimeError, match="tool exploded"):
        await agent.run("hola", "s1", on_event=events.append)

    result = next(e for e in events if e["type"] == "tool_result")
    assert result["ok"] is False


async def test_model_content_is_emitted_as_a_token():
    events = []
    agent = _make_agent(RecordingPattern([("model",)]), model_content="pensando en voz alta")
    await agent.run("hola", "s1", on_event=events.append)

    tokens = [e for e in events if e["type"] == "token"]
    assert tokens == [{"type": "token", "content": "pensando en voz alta"}]


async def test_empty_model_content_emits_no_token():
    events = []
    agent = _make_agent(RecordingPattern([("model",)]), model_content="")
    await agent.run("hola", "s1", on_event=events.append)

    assert [e for e in events if e["type"] == "token"] == []


async def test_the_engine_emits_no_status_or_done():
    """Those belong to the transport — a direct caller sees run() return."""
    events = []
    agent = _make_agent(RecordingPattern([("model",), ("tool", "a", {})]))
    await agent.run("hola", "s1", on_event=events.append)

    assert {e["type"] for e in events} == {"token", "tool_call", "tool_result"}


async def test_events_arrive_in_run_order():
    events = []
    agent = _make_agent(RecordingPattern([("model",), ("tool", "a", {}), ("model",)]))
    await agent.run("hola", "s1", on_event=events.append)

    assert [e["type"] for e in events] == [
        "token",
        "tool_call",
        "tool_result",
        "token",
    ]


async def test_without_on_event_the_run_behaves_exactly_as_before():
    """The regression that matters: every existing caller passes nothing."""
    agent = _make_agent(RecordingPattern([("model",), ("tool", "a", {})]))
    result = await agent.run("hola", "s1")
    assert result["answer"] == "done"


async def test_a_raising_observer_does_not_break_the_run():
    def boom(_event):
        raise RuntimeError("observer is broken")

    agent = _make_agent(RecordingPattern([("model",), ("tool", "a", {})]))
    result = await agent.run("hola", "s1", on_event=boom)
    assert result["answer"] == "done"
