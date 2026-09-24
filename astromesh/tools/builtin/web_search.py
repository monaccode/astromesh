"""Web search, web scrape, and Wikipedia built-in tools."""

import re
from typing import ClassVar
from urllib.parse import quote

import httpx

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult
from astromesh.tools.builtin._red import cliente_seguro, destino_bloqueado

_IDIOMA = re.compile(r"[a-z]{2,3}(-[a-z]{2,8})?")


class WebSearchTool(BuiltinTool):
    name = "web_search"
    description = "Search the web using a search API (Tavily, Brave, or SearXNG)"
    parameters: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Max results", "default": 5},
        },
        "required": ["query"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        query = arguments["query"]
        max_results = arguments.get("max_results", 5)
        provider = self.config.get("provider", "tavily")
        api_key = self.config.get("api_key") or context.secrets.get("SEARCH_API_KEY")
        if provider == "tavily":
            return await self._tavily_search(query, max_results, api_key)
        return ToolResult(success=False, data=None, error=f"Unknown provider: {provider}")

    async def _tavily_search(self, query: str, max_results: int, api_key: str | None) -> ToolResult:
        if not api_key:
            return ToolResult(success=False, data=None, error="Tavily api_key is required")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={"query": query, "max_results": max_results, "api_key": api_key},
                )
                data = resp.json()
                return ToolResult(
                    success=True,
                    data={"results": data.get("results", [])},
                    metadata={"provider": "tavily"},
                )
        except Exception as e:  # noqa: BLE001  (una tool que revienta degrada su llamada, nunca la corrida)
            return ToolResult(success=False, data=None, error=str(e))


class WebScrapeTool(BuiltinTool):
    name = "web_scrape"
    description = "Extract text content from a URL (HTML converted to plain text)"
    parameters: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "max_length": {"type": "integer", "default": 10000},
        },
        "required": ["url"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        url = arguments["url"]
        max_length = arguments.get("max_length", 10000)
        motivo = await destino_bloqueado(url)
        if motivo:
            return ToolResult(success=False, data=None, error=motivo)
        try:
            # El cliente chequea cada salto: un redirect a un destino interno
            # también se corta (tests/test_builtin_seguridad.py).
            async with cliente_seguro(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url)
                html = resp.text
                text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
                text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()[:max_length]
                return ToolResult(
                    success=True,
                    data={"content": text, "url": url, "length": len(text)},
                    metadata={"status_code": resp.status_code},
                )
        except Exception as e:  # noqa: BLE001  (una tool que revienta degrada su llamada, nunca la corrida)
            return ToolResult(success=False, data=None, error=str(e))


class WikipediaTool(BuiltinTool):
    name = "wikipedia"
    description = "Get a summary of a Wikipedia article"
    parameters: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "topic": {"type": "string"},
            "language": {"type": "string", "default": "en"},
        },
        "required": ["topic"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        topic = arguments["topic"]
        lang = arguments.get("language", "en")
        # El idioma arma el HOST: sin validarlo, el modelo elegía a dónde ir.
        if not isinstance(lang, str) or not _IDIOMA.fullmatch(lang):
            return ToolResult(success=False, data=None, error=f"Invalid language code: {lang!r}")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(str(topic), safe='')}"
                )
                if resp.status_code == 404:
                    return ToolResult(success=False, data=None, error=f"Article not found: {topic}")
                data = resp.json()
                return ToolResult(
                    success=True,
                    data={
                        "title": data.get("title"),
                        "extract": data.get("extract"),
                        "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
                    },
                    metadata={},
                )
        except Exception as e:  # noqa: BLE001  (una tool que revienta degrada su llamada, nunca la corrida)
            return ToolResult(success=False, data=None, error=str(e))
