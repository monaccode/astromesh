"""Astromesh ADK Quickstart — define and run an agent in 10 lines."""

import asyncio
from astromesh_adk import agent


@agent(name="assistant", model="ollama/llama3", description="General assistant")
async def assistant(ctx):
    """You are a helpful assistant. Be concise and accurate."""
    return None


async def main():
    result = await assistant.run("What is the capital of France?")
    print(f"Answer: {result.answer}")
    print(f"Cost: ${result.cost:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
