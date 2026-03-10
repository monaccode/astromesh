import pytest
from httpx import ASGITransport, AsyncClient

from astromesh.tools import ToolLoader
from astromesh.tools.base import BuiltinTool
from astromesh.tools.builtin import ALL_TOOLS
from astromesh.api.main import app


class TestAllToolsRegistry:
    def test_all_tools_has_17_entries(self):
        assert len(ALL_TOOLS) == 17

    def test_all_tools_are_builtin_subclasses(self):
        for tool_cls in ALL_TOOLS:
            assert issubclass(tool_cls, BuiltinTool), (
                f"{tool_cls.__name__} is not a BuiltinTool subclass"
            )

    def test_all_tools_have_unique_names(self):
        names = [cls.name for cls in ALL_TOOLS]
        assert len(names) == len(set(names)), f"Duplicate names found: {names}"

    def test_auto_discover_registers_all(self):
        loader = ToolLoader()
        loader.auto_discover()
        available = loader.list_available()
        assert len(available) == 17
        for tool_cls in ALL_TOOLS:
            assert tool_cls.name in available


class TestBuiltinToolsEndpoint:
    @pytest.fixture
    def client(self):
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    async def test_list_builtin_tools(self, client):
        async with client:
            resp = await client.get("/v1/tools/builtin")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 17
        assert len(body["tools"]) == 17

    async def test_builtin_tools_have_metadata(self, client):
        async with client:
            resp = await client.get("/v1/tools/builtin")
        tools = resp.json()["tools"]
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool
            assert len(tool["name"]) > 0
