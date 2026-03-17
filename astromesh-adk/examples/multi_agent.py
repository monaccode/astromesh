"""Astromesh ADK — multi-agent composition with AgentTeam."""

import asyncio
from astromesh_adk import agent, AgentTeam


@agent(name="researcher", model="ollama/llama3", description="Research specialist")
async def researcher(ctx):
    """You research topics thoroughly and provide factual summaries."""
    return None


@agent(name="writer", model="ollama/llama3", description="Content writer")
async def writer(ctx):
    """You write clear, engaging content from research notes."""
    return None


@agent(name="editor", model="ollama/llama3", description="Content editor")
async def editor(ctx):
    """You review and improve written content for clarity and accuracy."""
    return None


# Pipeline: research -> write -> edit
pipeline_team = AgentTeam(
    name="content-pipeline",
    pattern="pipeline",
    agents=[researcher, writer, editor],
)

# Supervisor: one agent delegates to others
supervisor_team = AgentTeam(
    name="content-supervisor",
    pattern="supervisor",
    supervisor=researcher,
    workers=[writer, editor],
)


async def main():
    result = await pipeline_team.run("Write an article about quantum computing")
    print(f"Pipeline result: {result.answer[:200]}...")


if __name__ == "__main__":
    asyncio.run(main())
