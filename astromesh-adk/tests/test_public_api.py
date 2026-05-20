def test_all_public_exports():
    """All documented public API names are importable from the top-level package."""
    from astromesh_adk import (
        Agent,
        AgentTeam,
        ADKRuntime,
        Callbacks,
        RunContext,
        RunResult,
        StreamEvent,
        Tool,
        ToolContext,
        agent,
        connect,
        disconnect,
        mcp_tools,
        remote,
        tool,
    )

    assert Agent is not None
    assert agent is not None
    assert tool is not None
    assert Tool is not None
    assert connect is not None
    assert disconnect is not None
    assert remote is not None
    assert AgentTeam is not None
    assert ADKRuntime is not None
    assert Callbacks is not None
    assert RunResult is not None
    assert RunContext is not None
    assert StreamEvent is not None
    assert ToolContext is not None
    assert mcp_tools is not None


def test_version():
    import astromesh_adk
    assert hasattr(astromesh_adk, "__version__")
    assert astromesh_adk.__version__ == "0.1.7"
