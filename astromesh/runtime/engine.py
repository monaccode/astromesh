from pathlib import Path
import yaml
from astromesh.core.memory import MemoryManager
from astromesh.core.model_router import ModelRouter
from astromesh.core.prompt_engine import PromptEngine
from astromesh.core.tools import ToolRegistry
from astromesh.orchestration.patterns import ReActPattern, PlanAndExecutePattern, ParallelFanOutPattern, PipelinePattern
from astromesh.orchestration.supervisor import SupervisorPattern
from astromesh.orchestration.swarm import SwarmPattern

class AgentRuntime:
    def __init__(self, config_dir="./config"):
        self._config_dir = Path(config_dir)
        self._agents: dict[str, "Agent"] = {}
        self._prompt_engine = PromptEngine()

    async def bootstrap(self):
        agents_dir = self._config_dir / "agents"
        if not agents_dir.exists():
            return
        for f in agents_dir.glob("*.agent.yaml"):
            config = yaml.safe_load(f.read_text())
            agent = self._build_agent(config)
            self._agents[agent.name] = agent

    def _build_agent(self, config):
        spec = config["spec"]
        metadata = config["metadata"]
        router = ModelRouter(spec.get("model", {}).get("routing", {"strategy": "cost_optimized"}))
        memory = MemoryManager(agent_id=metadata["name"], config=spec.get("memory", {}))
        tools = ToolRegistry()
        pattern_map = {
            "react": ReActPattern,
            "plan_and_execute": PlanAndExecutePattern,
            "parallel_fan_out": ParallelFanOutPattern,
            "pipeline": PipelinePattern,
            "supervisor": SupervisorPattern,
            "swarm": SwarmPattern,
        }
        pattern_name = spec.get("orchestration", {}).get("pattern", "react")
        pattern_cls = pattern_map.get(pattern_name, ReActPattern)
        pattern = pattern_cls()
        prompts = spec.get("prompts", {})
        for name, tmpl in prompts.get("templates", {}).items():
            self._prompt_engine.register_template(name, tmpl)
        return Agent(
            name=metadata["name"], version=metadata.get("version", "0.1.0"),
            namespace=metadata.get("namespace", "default"),
            description=spec.get("identity", {}).get("description", ""),
            router=router, memory=memory, tools=tools, pattern=pattern,
            system_prompt=prompts.get("system", ""), prompt_engine=self._prompt_engine,
            guardrails=spec.get("guardrails", {}), permissions=spec.get("permissions", {}),
            orchestration_config=spec.get("orchestration", {}),
        )

    async def run(self, agent_name, query, session_id, context=None):
        agent = self._agents.get(agent_name)
        if not agent:
            raise ValueError(f"Agent '{agent_name}' not found")
        return await agent.run(query, session_id, context)

    def list_agents(self):
        return [{"name": a.name, "version": a.version, "namespace": a.namespace} for a in self._agents.values()]


class Agent:
    def __init__(self, name, version, namespace, description, router, memory, tools,
                 pattern, system_prompt, prompt_engine, guardrails, permissions, orchestration_config):
        self.name = name
        self.version = version
        self.namespace = namespace
        self.description = description
        self._router = router
        self._memory = memory
        self._tools = tools
        self._pattern = pattern
        self._system_prompt = system_prompt
        self._prompt_engine = prompt_engine
        self._guardrails = guardrails
        self._permissions = permissions
        self._orchestration_config = orchestration_config

    async def run(self, query, session_id, context=None):
        from datetime import datetime
        from astromesh.core.memory import ConversationTurn

        query_text = query if isinstance(query, str) else " ".join(
            p.get("text", "") for p in query if p.get("type") == "text"
        )
        memory_context = await self._memory.build_context(session_id, query_text, max_tokens=4096)
        rendered_prompt = self._prompt_engine.render(self._system_prompt, {**(context or {}), "memory": memory_context})
        tool_schemas = self._tools.get_tool_schemas(self._permissions.get("allowed_actions"))
        max_iterations = self._orchestration_config.get("max_iterations", 10)

        async def model_fn(messages, tools):
            full_messages = [{"role": "system", "content": rendered_prompt}] + messages
            return await self._router.route(full_messages, tools=tools)

        async def tool_fn(name, args):
            return await self._tools.execute(name, args, {"agent": self.name, "session": session_id})

        result = await self._pattern.execute(query=query, context=memory_context, model_fn=model_fn,
            tool_fn=tool_fn, tools=tool_schemas, max_iterations=max_iterations)

        # Extract text for storage; keep full multimodal content in metadata.
        if isinstance(query, list):
            text_parts = [p.get("text", "") for p in query if p.get("type") == "text"]
            user_content = " ".join(text_parts)
            user_metadata = {"multimodal_content": query}
        else:
            user_content = query
            user_metadata = {}

        await self._memory.persist_turn(
            session_id,
            ConversationTurn(role="user", content=user_content, timestamp=datetime.utcnow(), metadata=user_metadata),
        )
        await self._memory.persist_turn(
            session_id,
            ConversationTurn(role="assistant", content=result.get("answer", ""), timestamp=datetime.utcnow()),
        )
        return result
