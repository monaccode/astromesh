import respx
import httpx
from astromesh.tools.base import ToolContext


def _ctx(**kwargs):
    return ToolContext(agent_name="test", session_id="s1", **kwargs)


class TestWebSearchTool:
    @respx.mock
    async def test_tavily_search(self):
        from astromesh.tools.builtin.web_search import WebSearchTool

        respx.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Python",
                            "url": "https://python.org",
                            "content": "The Python language",
                        }
                    ]
                },
            )
        )
        tool = WebSearchTool(config={"provider": "tavily", "api_key": "test-key"})
        result = await tool.execute({"query": "Python"}, _ctx())
        assert result.success is True
        assert len(result.data["results"]) == 1

    async def test_missing_api_key(self):
        from astromesh.tools.builtin.web_search import WebSearchTool

        tool = WebSearchTool(config={"provider": "tavily"})
        result = await tool.execute({"query": "test"}, _ctx(secrets={}))
        assert result.success is False


class TestWebScrapeTool:
    @respx.mock
    async def test_scrape_html(self):
        from astromesh.tools.builtin.web_search import WebScrapeTool

        respx.get("https://example.com").mock(
            return_value=httpx.Response(
                200, text="<html><body><h1>Hello</h1><p>World</p></body></html>"
            )
        )
        tool = WebScrapeTool()
        result = await tool.execute({"url": "https://example.com"}, _ctx())
        assert result.success is True
        assert "Hello" in result.data["content"]


class TestWikipediaTool:
    @respx.mock
    async def test_wikipedia_search(self):
        from astromesh.tools.builtin.web_search import WikipediaTool

        respx.get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/Python_(programming_language)"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "title": "Python",
                    "extract": "Python is a language.",
                    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Python"}},
                },
            )
        )
        tool = WikipediaTool()
        result = await tool.execute({"topic": "Python_(programming_language)"}, _ctx())
        assert result.success is True
        assert "Python" in result.data["title"]
