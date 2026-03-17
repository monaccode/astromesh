import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from astromesh_cloud.models.agent import Agent
from astromesh_cloud.services.config_builder import build_agent_config
from astromesh_cloud.services.runtime_proxy import RuntimeProxy

logger = logging.getLogger(__name__)

async def reconcile_agents(db: AsyncSession, proxy: RuntimeProxy) -> int:
    result = await db.execute(select(Agent).where(Agent.status == "deployed"))
    deployed = result.scalars().all()
    if not deployed:
        return 0
    try:
        runtime_agents = await proxy.list_agents()
        runtime_names = {a["name"] for a in runtime_agents}
    except Exception:
        runtime_names = set()
    count = 0
    for agent in deployed:
        if agent.runtime_name not in runtime_names:
            try:
                org_slug = agent.runtime_name.split("--")[0]
                config = build_agent_config(agent.config, org_slug)
                await proxy.register_agent(config)
                count += 1
            except Exception as e:
                logger.error(f"Reconciliation failed for {agent.runtime_name}: {e}")
    return count
