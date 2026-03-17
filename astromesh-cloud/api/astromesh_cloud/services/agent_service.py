from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from astromesh_cloud.models.agent import Agent


async def create_agent(db: AsyncSession, org_id: str, org_slug: str, config: dict) -> Agent:
    name = config["name"]
    runtime_name = f"{org_slug}--{name}"
    agent = Agent(
        org_id=org_id,
        name=name,
        display_name=config["display_name"],
        config=config,
        status="draft",
        runtime_name=runtime_name,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


async def get_agents(db: AsyncSession, org_id: str) -> list[Agent]:
    result = await db.execute(select(Agent).where(Agent.org_id == org_id))
    return list(result.scalars().all())


async def get_agent(db: AsyncSession, org_id: str, name: str) -> Agent | None:
    result = await db.execute(
        select(Agent).where(Agent.org_id == org_id, Agent.name == name)
    )
    return result.scalar_one_or_none()


async def count_deployed(db: AsyncSession, org_id: str) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Agent)
        .where(Agent.org_id == org_id, Agent.status == "deployed")
    )
    return result.scalar_one()


async def update_agent_status(
    db: AsyncSession,
    agent: Agent,
    status: str,
    deployed_at: datetime | None = None,
) -> Agent:
    agent.status = status
    if deployed_at:
        agent.deployed_at = deployed_at
    await db.commit()
    await db.refresh(agent)
    return agent
