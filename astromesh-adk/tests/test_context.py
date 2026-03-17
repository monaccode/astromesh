from datetime import datetime
from astromesh_adk.context import RunContext, ToolContext, MemoryAccessor


def test_run_context_creation():
    ctx = RunContext(
        query="Hello",
        session_id="s1",
        agent_name="test-agent",
        user_id="u1",
        timestamp=datetime(2026, 1, 1),
        metadata={"key": "value"},
        tools=["web_search"],
    )
    assert ctx.query == "Hello"
    assert ctx.session_id == "s1"
    assert ctx.agent_name == "test-agent"
    assert ctx.user_id == "u1"
    assert ctx.tools == ["web_search"]


def test_run_context_from_run_params():
    ctx = RunContext.from_run_params(
        query="Hello",
        session_id="s1",
        agent_name="test-agent",
        context={"user_id": "u1", "company": "Acme"},
        tool_names=["search"],
    )
    assert ctx.user_id == "u1"
    assert ctx.metadata["company"] == "Acme"
    assert ctx.tools == ["search"]
    assert isinstance(ctx.timestamp, datetime)


def test_run_context_from_run_params_no_context():
    ctx = RunContext.from_run_params(
        query="Hi",
        session_id="default",
        agent_name="agent",
        context=None,
        tool_names=[],
    )
    assert ctx.user_id is None
    assert ctx.metadata == {}


def test_tool_context_creation():
    ctx = ToolContext(agent_name="agent", session_id="s1")
    assert ctx.agent_name == "agent"
    assert ctx.session_id == "s1"
