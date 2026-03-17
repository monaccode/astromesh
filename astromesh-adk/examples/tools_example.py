"""Astromesh ADK — defining tools with decorators and classes."""

import asyncio
import httpx
from astromesh_adk import agent, tool, Tool


# Simple tool with decorator — schema auto-generated from type hints
@tool(description="Calculate a math expression")
async def calculator(expression: str) -> str:
    try:
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


# Stateful tool with class — for tools that need initialization
class WebFetcher(Tool):
    name = "web_fetch"
    description = "Fetch content from a URL"

    def __init__(self):
        self.client = httpx.AsyncClient()

    def parameters(self):
        return {
            "url": {"type": "string", "description": "URL to fetch"},
        }

    async def execute(self, args, ctx=None):
        resp = await self.client.get(args["url"], follow_redirects=True)
        return resp.text[:2000]

    async def cleanup(self):
        await self.client.aclose()


@agent(
    name="research-assistant",
    model="ollama/llama3",
    tools=[calculator, WebFetcher()],
    pattern="react",
)
async def research_assistant(ctx):
    """You are a research assistant with calculation and web capabilities."""
    return None


async def main():
    result = await research_assistant.run("What is 42 * 17?")
    print(f"Answer: {result.answer}")


if __name__ == "__main__":
    asyncio.run(main())
