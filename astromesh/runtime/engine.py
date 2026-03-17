from pathlib import Path
import yaml
from astromesh.core.memory import MemoryManager
from astromesh.core.model_router import ModelRouter
from astromesh.core.prompt_engine import PromptEngine
from astromesh.core.tools import ToolRegistry
from astromesh.orchestration.patterns import (
    ReActPattern,
    PlanAndExecutePattern,
    ParallelFanOutPattern,
    PipelinePattern,
)
from astromesh.orchestration.supervisor import SupervisorPattern
from astromesh.orchestration.swarm import SwarmPattern


def _make_builtin_handler(tool_instance, agent_name):
    """Create an async handler closure for a builtin tool instance."""

    async def _handler(**arguments):
        from astromesh.tools.base import ToolContext

        ctx = ToolContext(agent_name=agent_name, session_id="", trace_span=None)
        result = await tool_instance.execute(arguments, ctx)
        return result.to_dict()

    return _handler


class AgentRuntime:
    def __init__(self, config_dir="./config", service_manager=None, peer_client=None):
        self._config_dir = Path(config_dir)
        self._agents: dict[str, "Agent"] = {}
        self._prompt_engine = PromptEngine()
        self.service_manager = service_manager
        self.peer_client = peer_client

    async def bootstrap(self):
        # Skip agent loading if agents service is disabled
        if self.service_manager and not self.service_manager.is_enabled("agents"):
            return
        agents_dir = self._config_dir / "agents"
        if not agents_dir.exists():
            return
        configs = []
        for f in agents_dir.glob("*.agent.yaml"):
            configs.append(yaml.safe_load(f.read_text()))
        self._detect_circular_refs(configs)
        for config in configs:
            agent = self._build_agent(config)
            self._agents[agent.name] = agent

    def _detect_circular_refs(self, configs: list[dict]):
        """Detect circular agent-as-tool references. Raises ValueError if cycle found."""
        # Build adjacency list
        graph: dict[str, list[str]] = {}
        for config in configs:
            name = config["metadata"]["name"]
            agent_tools = [
                t["agent"]
                for t in config["spec"].get("tools", [])
                if t.get("type") == "agent"
            ]
            graph[name] = agent_tools

        # DFS cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {name: WHITE for name in graph}

        def dfs(node, path):
            color[node] = GRAY
            for neighbor in graph.get(node, []):
                if neighbor not in color:
                    continue  # references external agent, skip
                if color[neighbor] == GRAY:
                    cycle = path + [neighbor]
                    raise ValueError(
                        f"Circular agent reference detected: {' -> '.join(cycle)}"
                    )
                if color[neighbor] == WHITE:
                    dfs(neighbor, path + [neighbor])
            color[node] = BLACK

        for node in graph:
            if color[node] == WHITE:
                dfs(node, [node])

    def _build_agent(self, config):
        spec = config["spec"]
        metadata = config["metadata"]
        router = ModelRouter(spec.get("model", {}).get("routing", {"strategy": "cost_optimized"}))
        memory = MemoryManager(agent_id=metadata["name"], config=spec.get("memory", {}))
        tools = ToolRegistry()
        from astromesh.tools import ToolLoader

        loader = ToolLoader()
        loader.auto_discover()
        for tool_def in spec.get("tools", []):
            tool_type = tool_def.get("type", "internal")
            if tool_type == "builtin":
                instance = loader.create(tool_def["name"], config=tool_def.get("config"))
                handler = _make_builtin_handler(instance, metadata["name"])
                tools.register_internal(
                    name=tool_def["name"],
                    handler=handler,
                    description=instance.description,
                    parameters=instance.parameters,
                    rate_limit=tool_def.get("rate_limit"),
                )
            elif tool_type == "agent":
                tools.register_agent_tool(
                    name=tool_def["name"],
                    agent_name=tool_def["agent"],
                    description=tool_def.get(
                        "description",
                        f"Invoke agent '{tool_def['agent']}'",
                    ),
                    parameters=tool_def.get("parameters"),
                    context_transform=tool_def.get("context_transform"),
                )
                tools.set_runtime(self)
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
            name=metadata["name"],
            version=metadata.get("version", "0.1.0"),
            namespace=metadata.get("namespace", "default"),
            description=spec.get("identity", {}).get("description", ""),
            router=router,
            memory=memory,
            tools=tools,
            pattern=pattern,
            system_prompt=prompts.get("system", ""),
            prompt_engine=self._prompt_engine,
            guardrails=spec.get("guardrails", {}),
            permissions=spec.get("permissions", {}),
            orchestration_config=spec.get("orchestration", {}),
        )

    async def run(self, agent_name, query, session_id, context=None, parent_trace_id=None):
        agent = self._agents.get(agent_name)
        if not agent:
            raise ValueError(f"Agent '{agent_name}' not found")
        return await agent.run(query, session_id, context, parent_trace_id=parent_trace_id)

    def list_agents(self):
        return [
            {"name": a.name, "version": a.version, "namespace": a.namespace}
            for a in self._agents.values()
        ]

    async def register_agent(self, config: dict) -> None:
        """Register an agent dynamically from a config dict (same schema as YAML).
        If an agent with the same name exists, it is overwritten (upsert semantics
        required by reconciliation loop and re-deploy flows)."""
        name = config.get("metadata", {}).get("name") or config.get("spec", {}).get("identity", {}).get("name")
        if not name:
            raise ValueError("Agent config must include metadata.name or spec.identity.name")
        agent = self._build_agent(config)
        self._agents[agent.name] = agent

    def unregister_agent(self, name: str) -> None:
        """Remove a dynamically registered agent."""
        if name not in self._agents:
            raise ValueError(f"Agent '{name}' not found")
        del self._agents[name]


class Agent:
    def __init__(
        self,
        name,
        version,
        namespace,
        description,
        router,
        memory,
        tools,
        pattern,
        system_prompt,
        prompt_engine,
        guardrails,
        permissions,
        orchestration_config,
    ):
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

    async def run(self, query, session_id, context=None, parent_trace_id=None):
        from datetime import datetime
        from astromesh.core.memory import ConversationTurn
        from astromesh.observability.tracing import TracingContext, SpanStatus

        tracing = TracingContext(agent_name=self.name, session_id=session_id)
        if parent_trace_id:
            tracing.trace_id = parent_trace_id  # share trace tree
        root_span = tracing.start_span("agent.run", {"agent": self.name, "session": session_id})

        try:
            query_text = (
                query
                if isinstance(query, str)
                else " ".join(p.get("text", "") for p in query if p.get("type") == "text")
            )

            mem_span = tracing.start_span("memory_build")
            memory_context = await self._memory.build_context(
                session_id, query_text, max_tokens=4096
            )
            tracing.finish_span(mem_span)

            prompt_span = tracing.start_span("prompt_render")
            rendered_prompt = self._prompt_engine.render(
                self._system_prompt, {**(context or {}), "memory": memory_context}
            )
            tracing.finish_span(prompt_span)

            tool_schemas = self._tools.get_tool_schemas(self._permissions.get("allowed_actions"))
            max_iterations = self._orchestration_config.get("max_iterations", 10)

            route_kwargs = {}
            provider_override_config = (context or {}).get("_provider_override")
            if provider_override_config:
                from astromesh.providers.factory import create_provider

                override_name = provider_override_config["name"]
                override_key = provider_override_config["key"]
                override_provider = create_provider(override_name, api_key=override_key)
                route_kwargs["provider_override"] = (override_name, override_provider)

            async def model_fn(messages, tools):
                llm_span = tracing.start_span(
                    "llm.complete", parent_span_id=root_span.span_id
                )
                full_messages = [{"role": "system", "content": rendered_prompt}] + messages
                try:
                    response = await self._router.route(full_messages, tools=tools, **route_kwargs)
                    if hasattr(response, "usage") and response.usage:
                        llm_span.set_attribute(
                            "input_tokens", response.usage.get("input_tokens", 0)
                        )
                        llm_span.set_attribute(
                            "output_tokens", response.usage.get("output_tokens", 0)
                        )
                    tracing.finish_span(llm_span)
                    return response
                except Exception:
                    tracing.finish_span(llm_span, status=SpanStatus.ERROR)
                    raise

            async def tool_fn(name, args):
                tool_span = tracing.start_span(
                    "tool.call", {"tool": name}, parent_span_id=root_span.span_id
                )
                try:
                    observation = await self._tools.execute(
                        name, args, {"agent": self.name, "session": session_id}
                    )
                    tracing.finish_span(tool_span)
                    return observation
                except Exception:
                    tracing.finish_span(tool_span, status=SpanStatus.ERROR)
                    raise

            orch_span = tracing.start_span(
                "orchestration",
                {"pattern": self._orchestration_config.get("pattern", "react")},
                parent_span_id=root_span.span_id,
            )
            result = await self._pattern.execute(
                query=query,
                context=memory_context,
                model_fn=model_fn,
                tool_fn=tool_fn,
                tools=tool_schemas,
                max_iterations=max_iterations,
            )
            tracing.finish_span(orch_span)

            # Extract text for storage; keep full multimodal content in metadata.
            if isinstance(query, list):
                text_parts = [p.get("text", "") for p in query if p.get("type") == "text"]
                user_content = " ".join(text_parts)
                user_metadata = {"multimodal_content": query}
            else:
                user_content = query
                user_metadata = {}

            persist_span = tracing.start_span(
                "memory_persist", parent_span_id=root_span.span_id
            )
            await self._memory.persist_turn(
                session_id,
                ConversationTurn(
                    role="user",
                    content=user_content,
                    timestamp=datetime.utcnow(),
                    metadata=user_metadata,
                ),
            )
            await self._memory.persist_turn(
                session_id,
                ConversationTurn(
                    role="assistant",
                    content=result.get("answer", ""),
                    timestamp=datetime.utcnow(),
                ),
            )
            tracing.finish_span(persist_span)

            tracing.finish_span(root_span)
            result["trace"] = tracing.to_dict()
            return result

        except Exception:
            tracing.finish_span(root_span, status=SpanStatus.ERROR)
            raise
