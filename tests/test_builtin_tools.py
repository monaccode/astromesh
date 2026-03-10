import httpx as httpx_lib
import respx

from astromesh.tools.base import ToolContext


def _ctx(**kwargs) -> ToolContext:
    return ToolContext(agent_name="test", session_id="s1", **kwargs)


class TestDatetimeNowTool:
    async def test_returns_current_time(self):
        from astromesh.tools.builtin.utilities import DatetimeNowTool

        tool = DatetimeNowTool()
        result = await tool.execute({"timezone": "UTC"}, _ctx())
        assert result.success is True
        assert "datetime" in result.data
        assert "UTC" in result.data["timezone"]

    async def test_default_timezone(self):
        from astromesh.tools.builtin.utilities import DatetimeNowTool

        tool = DatetimeNowTool()
        result = await tool.execute({}, _ctx())
        assert result.success is True


class TestJsonTransformTool:
    async def test_jinja2_transform(self):
        from astromesh.tools.builtin.utilities import JsonTransformTool

        tool = JsonTransformTool()
        result = await tool.execute(
            {
                "data": {"name": "Alice", "scores": [90, 85]},
                "template": '{"greeting": "Hello {{ data.name }}", "top_score": {{ data.scores[0] }}}',
            },
            _ctx(),
        )
        assert result.success is True
        assert result.data["greeting"] == "Hello Alice"
        assert result.data["top_score"] == 90

    async def test_invalid_template(self):
        from astromesh.tools.builtin.utilities import JsonTransformTool

        tool = JsonTransformTool()
        result = await tool.execute(
            {"data": {}, "template": "{{ invalid | no_such_filter }}"}, _ctx()
        )
        assert result.success is False


class TestCacheStoreTool:
    async def test_set_and_get(self):
        from astromesh.tools.builtin.utilities import CacheStoreTool

        tool = CacheStoreTool()
        cache = {}
        ctx = _ctx(cache=cache)
        result = await tool.execute({"action": "set", "key": "mykey", "value": "myval"}, ctx)
        assert result.success is True
        result = await tool.execute({"action": "get", "key": "mykey"}, ctx)
        assert result.success is True
        assert result.data == "myval"

    async def test_get_missing_key(self):
        from astromesh.tools.builtin.utilities import CacheStoreTool

        tool = CacheStoreTool()
        result = await tool.execute({"action": "get", "key": "nope"}, _ctx(cache={}))
        assert result.success is True
        assert result.data is None

    async def test_delete(self):
        from astromesh.tools.builtin.utilities import CacheStoreTool

        tool = CacheStoreTool()
        cache = {"k": "v"}
        result = await tool.execute({"action": "delete", "key": "k"}, _ctx(cache=cache))
        assert result.success is True
        assert "k" not in cache


class TestHttpRequestTool:
    @respx.mock
    async def test_get_request(self):
        from astromesh.tools.builtin.http import HttpRequestTool

        respx.get("https://api.example.com/data").mock(
            return_value=httpx_lib.Response(200, json={"result": "ok"})
        )
        tool = HttpRequestTool()
        result = await tool.execute(
            {"method": "GET", "url": "https://api.example.com/data"}, _ctx()
        )
        assert result.success is True
        assert result.data["status_code"] == 200
        assert result.data["body"]["result"] == "ok"

    @respx.mock
    async def test_post_with_body(self):
        from astromesh.tools.builtin.http import HttpRequestTool

        respx.post("https://api.example.com/submit").mock(
            return_value=httpx_lib.Response(201, json={"id": 1})
        )
        tool = HttpRequestTool()
        result = await tool.execute(
            {
                "method": "POST",
                "url": "https://api.example.com/submit",
                "body": {"name": "test"},
            },
            _ctx(),
        )
        assert result.success is True
        assert result.data["status_code"] == 201

    async def test_blocks_localhost_by_default(self):
        from astromesh.tools.builtin.http import HttpRequestTool

        tool = HttpRequestTool()
        result = await tool.execute(
            {"method": "GET", "url": "http://localhost:8080/secret"}, _ctx()
        )
        assert result.success is False

    @respx.mock
    async def test_timeout(self):
        from astromesh.tools.builtin.http import HttpRequestTool

        respx.get("https://slow.example.com").mock(side_effect=httpx_lib.ReadTimeout("timeout"))
        tool = HttpRequestTool(config={"timeout_seconds": 1})
        result = await tool.execute({"method": "GET", "url": "https://slow.example.com"}, _ctx())
        assert result.success is False


class TestGraphQLQueryTool:
    @respx.mock
    async def test_graphql_query(self):
        from astromesh.tools.builtin.http import GraphQLQueryTool

        respx.post("https://api.example.com/graphql").mock(
            return_value=httpx_lib.Response(200, json={"data": {"user": {"name": "Alice"}}})
        )
        tool = GraphQLQueryTool()
        result = await tool.execute(
            {
                "endpoint": "https://api.example.com/graphql",
                "query": "query { user { name } }",
            },
            _ctx(),
        )
        assert result.success is True
        assert result.data["data"]["user"]["name"] == "Alice"
