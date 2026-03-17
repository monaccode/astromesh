from astromesh_adk.mcp import mcp_tools, MCPToolSet


def test_mcp_tools_returns_toolset():
    toolset = mcp_tools(transport="stdio", command="echo", args=["hello"])
    assert isinstance(toolset, MCPToolSet)


def test_mcp_toolset_is_iterable():
    toolset = mcp_tools(transport="stdio", command="echo", args=[])
    # Before discovery, iteration yields the toolset itself as a lazy marker
    items = list(toolset)
    assert len(items) == 1
    assert items[0] is toolset


def test_mcp_toolset_stores_config():
    toolset = mcp_tools(
        transport="http",
        command=None,
        args=[],
        url="https://mcp.example.com",
        headers={"Authorization": "Bearer xxx"},
    )
    assert toolset.config["transport"] == "http"
    assert toolset.config["url"] == "https://mcp.example.com"


def test_mcp_toolset_discovered_flag():
    toolset = mcp_tools(transport="stdio", command="echo", args=[])
    assert toolset.discovered is False
