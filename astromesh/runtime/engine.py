import json
import logging
import os
import uuid
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
from astromesh.runtime.provider_registry import load_provider_registry, resolve_block

logger = logging.getLogger(__name__)


def _emit(on_event, event: dict) -> None:
    """Hand one event to the caller's observer, if there is one.

    An observer that raises is logged and ignored: watching a run must never be
    able to break it. This mirrors ChannelEventBus.emit(), which likewise
    swallows a subscriber's failure rather than propagating it into the producer.
    """
    if on_event is None:
        return
    try:
        on_event(event)
    except Exception:
        logger.exception("on_event callback raised; ignoring")


def _agent_disk_persist_enabled() -> bool:
    return os.environ.get("ASTROMESH_PERSIST_AGENTS", "1").lower() not in (
        "0",
        "false",
        "no",
    )


def _validate_agent_filesystem_name(name: str) -> None:
    if not name or not isinstance(name, str):
        raise ValueError("Invalid agent name")
    if name != Path(name).name or ".." in name:
        raise ValueError("Invalid agent name")


def _make_builtin_handler(tool_instance, agent_name, rag_pipeline=None):
    """Create an async handler closure for a builtin tool instance."""

    async def _handler(**arguments):
        from astromesh.tools.base import ToolContext

        ctx = ToolContext(agent_name=agent_name, session_id="", trace_span=None)
        ctx.rag_pipeline = rag_pipeline
        result = await tool_instance.execute(arguments, ctx)
        return result.to_dict()

    return _handler


class _InvalidToolParameters(Exception):
    """Raised by _normalize_tool_parameters when `parameters` is present but not
    a mapping (e.g. a YAML list, string, int or bool). Carries the offending
    type's name so the caller can name it in a warning."""

    def __init__(self, actual_type: str):
        self.actual_type = actual_type
        super().__init__(actual_type)


def _normalize_tool_parameters(parameters: dict | None) -> dict | None:
    """Turn a YAML-authored 'parameters' block into valid JSON Schema.

    Every shipped agent YAML writes tool parameters in a shorthand — a flat
    mapping of param name -> {type, description}, e.g.:

        parameters:
          company_name:
            type: string
            description: "Company name to look up"

    That is not JSON Schema: it has no `type: object` and no `properties`
    wrapper. Passed through untouched, it reaches the model exactly as
    written, and a provider that validates function-calling schemas
    (Anthropic's input_schema requires `type: object`; OpenAI strict mode
    rejects the shape outright) 400s the whole request — not just that one
    tool. This wraps the shorthand into `{"type": "object", "properties":
    {...}}` so what the model receives is always valid.

    Idempotent: the real invariant is "a mapping that declares `type: object`
    is already JSON Schema" — full stop, whether or not it also carries a
    `properties` key. A bare `{type: object}` (a valid no-arg tool schema) is
    returned with `properties` defaulted to `{}`; any other keys already
    present (`properties`, `required`, `additionalProperties`, ...) are kept
    exactly as written. So a YAML author who writes real JSON Schema is never
    rewritten out from under them.

    `None` (parameters omitted from YAML entirely) passes through as `None`
    so each register_* call's own default parameter set still applies.

    The shorthand has no way to express `required`; nothing is inferred, so
    a shorthand-normalized schema simply has no `required` key (valid JSON
    Schema — `required` is optional).

    Raises `_InvalidToolParameters` if `parameters` is neither `None` nor a
    mapping — YAML can express `parameters: [a, b]` or a bare scalar just as
    easily as a mapping, and blindly calling `.get()` on it would raise
    `AttributeError` and take the whole agent down with it (caught by
    `load_agents`'s broad `except`, but that degrades an agent to `draft`
    over one malformed tool declaration). The caller in the tools loop below
    catches this and treats it like any other unsupported tool shape: warns,
    naming the agent and the tool, and skips just that tool.

    Lives here, not in ToolRegistry.register_client_tool, because this is
    where YAML enters the runtime for every tool type — 'client' is the
    first to hit this bug because it's the first type where YAML-authored
    'parameters' reach the model verbatim, but 'agent' would hit the exact
    same bug the moment any YAML declares 'parameters' on an agent tool.
    A normalizer placed in register_client_tool would only ever cover
    client tools; this one is available to any branch of the tools loop
    below that decides it needs it.
    """
    if parameters is None:
        return None
    if not isinstance(parameters, dict):
        raise _InvalidToolParameters(type(parameters).__name__)
    if parameters.get("type") == "object":
        normalized = dict(parameters)
        normalized.setdefault("properties", {})
        return normalized
    return {"type": "object", "properties": parameters}


def _truncate(text: str | None, limit: int) -> str:
    """Truncate text to limit chars, appending a marker if truncated."""
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated at {len(text)} chars]"


def _parse_args(args):
    """Parse arguments that may be a JSON string (OpenAI) or already a dict."""
    if isinstance(args, str):
        try:
            return json.loads(args)
        except (json.JSONDecodeError, ValueError):
            return {"_raw": args}
    return args


def _normalize_tool_calls(raw_calls: list) -> list[dict]:
    """Normalize tool_calls to plain JSON-serializable dicts."""
    normalized = []
    for tc in raw_calls:
        if isinstance(tc, dict):
            if "function" in tc:
                normalized.append(
                    {
                        "id": tc.get("id"),
                        "name": tc["function"]["name"],
                        "arguments": _parse_args(tc["function"].get("arguments", {})),
                    }
                )
            else:
                normalized.append(tc)
        else:
            normalized.append({"raw": str(tc)})
    return normalized


# Keys each source's wiring below actually reads. Anything else an agent
# declares is dropped on the floor, which is how the `timeout` and `parameters`
# bugs survived 35 releases: the schema accepted them and nobody said a word.
# `temperature`/`max_tokens` are the documented top-level shorthand, folded into
# `parameters` by _model_parameters() for the sources that take parameters.
_SELECTOR_KEYS = frozenset({"source", "provider", "model", "providerRef"})
_SHORTHAND_KEYS = ("temperature", "max_tokens")
_PARAMETER_KEYS = frozenset({"parameters", "timeout", *_SHORTHAND_KEYS})
_CONSUMED_KEYS: dict[str, frozenset[str]] = {
    "ollama": _SELECTOR_KEYS | _PARAMETER_KEYS | {"endpoint"},
    "openai_compat": _SELECTOR_KEYS | _PARAMETER_KEYS | {"endpoint", "api_key", "api_key_env"},
    "litellm": _SELECTOR_KEYS | _PARAMETER_KEYS | {"api_key", "api_key_env"},
    "centinela": _SELECTOR_KEYS
    | {
        "endpoint",
        "endpoint_name",
        "api_key",
        "api_key_env",
        "contract",
        "invalid_policy",
        "max_retries",
    },
}
_CONSUMED_KEYS["openai"] = _CONSUMED_KEYS["openai_compat"]
_CONSUMED_KEYS["azure_openai"] = _CONSUMED_KEYS["openai_compat"]


def _model_parameters(block: dict) -> dict | None:
    """Merge the top-level `temperature`/`max_tokens` shorthand into `parameters`.

    The agent schema documents both as "top-level shorthand for
    parameters.<name>", but nothing ever read them. An explicit entry under
    `parameters` wins over the shorthand.
    """
    params = dict(block.get("parameters") or {})
    for key in _SHORTHAND_KEYS:
        if block.get(key) is not None:
            params.setdefault(key, block[key])
    return params or None


def _warn_unconsumed_keys(block: dict, source: str) -> None:
    """Warn about keys this source's wiring will ignore.

    Only non-None values count: resolve_block() injects endpoint/contract/... as
    None for every source, and warning on those would fire for every providerRef
    block and teach everyone to tune the warning out.
    """
    consumed = _CONSUMED_KEYS.get(source)
    if consumed is None:
        return
    ignored = sorted(k for k, v in block.items() if v is not None and k not in consumed)
    if ignored:
        logger.warning(
            "model block for source %r declares %s, which this source does not use; "
            "the value(s) will be ignored",
            source,
            ", ".join(repr(k) for k in ignored),
        )


def build_candidate_provider(block: dict):
    """Build a provider instance from a candidate/legacy block.

    Accepts `source` (new) or `provider` (legacy) to select the adapter. When
    neither is set, infers `litellm` for prefixed models (contain '/') and
    `openai_compat` otherwise. Returns None for unknown sources, and also for
    `litellm` when the optional `litellm` dependency is not installed (probed
    eagerly here so registration fails loudly instead of only at `complete()`).
    """
    from astromesh.providers.ollama_provider import OllamaProvider
    from astromesh.providers.openai_compat import OpenAICompatProvider

    source = (block.get("source") or block.get("provider") or "").strip().lower()
    model = block.get("model", "")
    if not source:
        source = "litellm" if "/" in model else "openai_compat"

    _warn_unconsumed_keys(block, source)

    if source == "ollama":
        base = (block.get("endpoint") or "http://localhost:11434").rstrip("/")
        return OllamaProvider(
            config={
                "base_url": base,
                "model": model or "llama3",
                "parameters": _model_parameters(block),
                "timeout": float(block.get("timeout", 120)),
            }
        )
    if source in ("openai_compat", "openai", "azure_openai"):
        base = (block.get("endpoint") or "https://api.openai.com/v1").rstrip("/")
        return OpenAICompatProvider(
            config={
                "base_url": base,
                "model": model or "gpt-4o-mini",
                "api_key_env": block.get("api_key_env", "OPENAI_API_KEY"),
                "api_key": block.get("api_key"),
                "parameters": _model_parameters(block),
                "timeout": float(block.get("timeout", 120)),
            }
        )
    if source == "litellm":
        from astromesh.providers import litellm_provider as _llm

        try:
            _llm._import_litellm()
        except Exception:
            logger.warning(
                "litellm not installed; skipping candidate model %r (install the 'litellm' extra)",
                model,
            )
            return None
        return _llm.LiteLLMProvider(
            config={
                "model": model or "gpt-4o",
                "api_key": block.get("api_key"),
                "api_key_env": block.get("api_key_env"),
                "parameters": _model_parameters(block),
                "timeout": float(block.get("timeout", 120)),
            }
        )
    if source == "centinela":
        from astromesh.providers.centinela import CentinelaProvider

        return CentinelaProvider(
            config={
                "endpoint": block.get("endpoint"),
                "endpoint_name": block.get("endpoint_name"),
                "api_key": block.get("api_key"),
                "api_key_env": block.get("api_key_env"),
                "model": model or "centinela",
                "contract": block.get("contract") or {},
                "invalid_policy": block.get("invalid_policy", "mark"),
                "max_retries": int(block.get("max_retries", 1)),
            }
        )
    return None


class AgentRuntime:
    def __init__(
        self,
        config_dir="./config",
        service_manager=None,
        peer_client=None,
        observability=None,
    ):
        self._config_dir = Path(config_dir)
        self._provider_registry = load_provider_registry(self._config_dir)
        self._rag_specs = {}
        self._agents: dict[str, "Agent"] = {}
        self._agent_status: dict[str, str] = {}
        self._agent_configs: dict[str, dict] = {}
        self._prompt_engine = PromptEngine()
        self.service_manager = service_manager
        self.peer_client = peer_client
        self._observability = observability or {}

    async def bootstrap(self):
        # Wire OTLP export FIRST: the early returns below must not leave a deployment untraced.
        # Imported lazily — the module pulls in the traces route (FastAPI) on the enabled path.
        from astromesh.observability.setup import setup_observability

        setup_observability(self._observability)

        # Skip agent loading if agents service is disabled
        if self.service_manager and not self.service_manager.is_enabled("agents"):
            return
        agents_dir = self._config_dir / "agents"
        if not agents_dir.exists():
            return
        from astromesh.rag.loader import RAGPipelineLoader

        self._rag_specs = RAGPipelineLoader(str(self._config_dir / "rag")).load_all()
        configs = []
        for f in agents_dir.glob("*.agent.yaml"):
            configs.append(yaml.safe_load(f.read_text()))
        self._detect_circular_refs(configs)
        for config in configs:
            name = config.get("metadata", {}).get("name", "<unknown>")
            try:
                agent = self._build_agent(config)
            except Exception:
                logger.exception("Skipping agent %s: failed to build from config", name)
                if name and name != "<unknown>":
                    self._agent_configs[name] = config
                    self._agent_status[name] = "draft"
                continue
            self._agents[agent.name] = agent
            self._agent_configs[name] = config
            self._agent_status[name] = "deployed"

    def _detect_circular_refs(self, configs: list[dict]):
        """Detect circular agent-as-tool references. Raises ValueError if cycle found."""
        # Build adjacency list
        graph: dict[str, list[str]] = {}
        for config in configs:
            name = config["metadata"]["name"]
            agent_tools = [
                t["agent"] for t in config["spec"].get("tools", []) if t.get("type") == "agent"
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
                    raise ValueError(f"Circular agent reference detected: {' -> '.join(cycle)}")
                if color[neighbor] == WHITE:
                    dfs(neighbor, path + [neighbor])
            color[node] = BLACK

        for node in graph:
            if color[node] == WHITE:
                dfs(node, [node])

    def _normalize_model_spec(self, model_spec: dict) -> dict[str, dict]:
        """Normalize legacy and new model schemas into {role: {candidates, strategy}}.

        Always returns a 'default' role. Legacy primary/fallback/extra/routing
        collapse into 'default'; the new schema uses model.default + model.roles.
        """
        roles: dict[str, dict] = {}

        # New schema
        if "default" in model_spec or "roles" in model_spec:
            default_block = model_spec.get("default") or {}
            roles["default"] = {
                "candidates": list(default_block.get("candidates", [])),
                "strategy": default_block.get("strategy", "cost_optimized"),
            }
            for name, block in (model_spec.get("roles") or {}).items():
                if name == "default":
                    continue
                roles[str(name)] = {
                    "candidates": list((block or {}).get("candidates", [])),
                    "strategy": (block or {}).get("strategy", "cost_optimized"),
                }
            return roles

        # Legacy schema → single 'default' role
        candidates: list[dict] = []
        for slot in ("primary", "fallback"):
            block = model_spec.get(slot)
            if isinstance(block, dict) and (block.get("provider") or block.get("source")):
                candidates.append(block)
        extras = model_spec.get("extra")
        if isinstance(extras, dict):
            for block in extras.values():
                if isinstance(block, dict) and (block.get("provider") or block.get("source")):
                    candidates.append(block)
        strategy = (model_spec.get("routing") or {}).get("strategy", "cost_optimized")
        roles["default"] = {"candidates": candidates, "strategy": strategy}
        return roles

    def _build_role_routers(self, model_spec: dict) -> dict[str, "ModelRouter"]:
        """Build one ModelRouter per role from the normalized spec."""
        roles = self._normalize_model_spec(model_spec)
        routers: dict[str, ModelRouter] = {}
        for role_name, cfg in roles.items():
            router = ModelRouter({"strategy": cfg.get("strategy", "cost_optimized")})
            registered = 0
            for i, block in enumerate(cfg.get("candidates", [])):
                block = resolve_block(block, self._provider_registry)
                try:
                    prov = build_candidate_provider(block)
                except Exception:
                    logger.exception("role %s candidate %d failed to build", role_name, i)
                    continue
                if prov is None:
                    logger.warning(
                        "role %s candidate %d (source %r) not registered; skipping",
                        role_name,
                        i,
                        block.get("source") or block.get("provider"),
                    )
                    continue
                router.register_provider(f"cand{i}", prov)
                registered += 1
            if registered == 0 and role_name != "default":
                logger.warning(
                    "role %s registered 0 providers; requests to it will fall back to 'default'",
                    role_name,
                )
                continue
            if registered == 0:
                logger.warning("role %s registered 0 providers", role_name)
            routers[role_name] = router
        if "default" not in routers:
            routers["default"] = ModelRouter({"strategy": "cost_optimized"})
        return routers

    def _resolve_rag(self, spec: dict):
        from astromesh.rag.agent_rag import AgentRAG
        from astromesh.rag.factory import build_pipeline

        knowledge = spec.get("knowledge") or {}
        name = knowledge.get("pipeline")
        if not name:
            return None
        rag_spec = self._rag_specs.get(name)
        if rag_spec is None:
            logger.warning("agent references unknown RAGPipeline '%s'; skipping KB", name)
            return None
        try:
            pipeline = build_pipeline(rag_spec)
        except Exception:
            logger.warning("failed to build RAGPipeline '%s'; skipping KB", name, exc_info=True)
            return None
        top_k = knowledge.get("top_k", rag_spec.retrieval.get("top_k", 5))
        return AgentRAG(pipeline, top_k=top_k)

    def _build_agent(self, config):
        spec = config["spec"]
        metadata = config["metadata"]
        model_spec = spec.get("model", {})
        routers = self._build_role_routers(model_spec)
        memory = MemoryManager(agent_id=metadata["name"], config=spec.get("memory", {}))
        rag = self._resolve_rag(spec)
        tools = ToolRegistry()
        from astromesh.tools import ToolLoader

        loader = ToolLoader()
        loader.auto_discover()
        for tool_def in spec.get("tools", []):
            tool_type = tool_def.get("type", "internal")
            if tool_type == "builtin":
                instance = loader.create(tool_def["name"], config=tool_def.get("config"))
                handler = _make_builtin_handler(
                    instance, metadata["name"], rag_pipeline=(rag.pipeline if rag else None)
                )
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
            elif tool_type == "client":
                try:
                    normalized_parameters = _normalize_tool_parameters(tool_def.get("parameters"))
                except _InvalidToolParameters as exc:
                    # Same warn-don't-break stance as the unsupported-type branch below:
                    # a malformed 'parameters' block on one tool must not degrade the
                    # whole agent to 'draft'. Names the agent, the tool, and what was
                    # wrong, then skips just this tool.
                    logger.warning(
                        "agent %r declares tool %r with parameters of type %r — "
                        "expected a mapping (YAML shorthand or JSON Schema), ignoring it.",
                        metadata["name"],
                        tool_def.get("name"),
                        exc.actual_type,
                    )
                    continue
                tools.register_client_tool(
                    name=tool_def["name"],
                    description=tool_def.get("description", ""),
                    parameters=normalized_parameters,
                    rate_limit=tool_def.get("rate_limit"),
                )
            else:
                # Until 0.35.0 this fell off the end of the chain in silence: the tool
                # was never registered, never reached the model, and nothing said so —
                # you got an agent with no tools and nothing to look at. 'internal' is
                # the default type, so a tool with no 'type' landed here too.
                # It warns rather than raises: raising would stop bootstrap() for every
                # existing YAML that declares one. The error comes in 1.0.
                logger.warning(
                    "agent %r declares tool %r with unsupported type %r — ignoring it. "
                    "YAML supports: builtin, agent, client.",
                    metadata["name"],
                    tool_def.get("name"),
                    tool_type,
                )
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
            routers=routers,
            memory=memory,
            tools=tools,
            pattern=pattern,
            system_prompt=prompts.get("system", ""),
            prompt_engine=self._prompt_engine,
            guardrails=spec.get("guardrails", {}),
            permissions=spec.get("permissions", {}),
            orchestration_config=spec.get("orchestration", {}),
            rag=rag,
        )

    async def run(
        self, agent_name, query, session_id, context=None, parent_trace_id=None, on_event=None
    ):
        agent = self._agents.get(agent_name)
        if not agent:
            raise ValueError(f"Agent '{agent_name}' not found")
        return await agent.run(
            query, session_id, context, parent_trace_id=parent_trace_id, on_event=on_event
        )

    def list_agents(self):
        result = []
        seen = set()
        # Include deployed agents from _agents
        for a in self._agents.values():
            result.append(
                {
                    "name": a.name,
                    "version": a.version,
                    "namespace": a.namespace,
                    "status": self._agent_status.get(a.name, "deployed"),
                }
            )
            seen.add(a.name)
        # Include non-deployed agents from _agent_configs
        for name, config in self._agent_configs.items():
            if name not in seen:
                metadata = config.get("metadata", {})
                result.append(
                    {
                        "name": name,
                        "version": metadata.get("version", "0.1.0"),
                        "namespace": metadata.get("namespace", "default"),
                        "status": self._agent_status.get(name, "draft"),
                    }
                )
        return result

    def _agent_yaml_path(self, name: str) -> Path:
        _validate_agent_filesystem_name(name)
        return self._config_dir / "agents" / f"{name}.agent.yaml"

    def _persist_agent_yaml(self, name: str, config: dict) -> None:
        if not _agent_disk_persist_enabled():
            return
        path = self._agent_yaml_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    def _remove_agent_yaml(self, name: str) -> None:
        if not _agent_disk_persist_enabled():
            return
        try:
            path = self._agent_yaml_path(name)
        except ValueError:
            return
        if path.is_file():
            path.unlink()

    async def register_agent(self, config: dict) -> None:
        """Register an agent dynamically from a config dict (same schema as YAML).
        Stores the config and sets status to 'draft' without building the agent.
        The agent must be explicitly deployed via deploy_agent()."""
        name = config.get("metadata", {}).get("name") or config.get("spec", {}).get(
            "identity", {}
        ).get("name")
        if not name:
            raise ValueError("Agent config must include metadata.name or spec.identity.name")
        self._agent_configs[name] = config
        self._agent_status[name] = "draft"
        self._persist_agent_yaml(name, config)

    async def deploy_agent(self, name: str) -> None:
        """Build and deploy a registered agent, making it available for execution."""
        if name not in self._agent_configs:
            raise ValueError(f"Agent '{name}' not found")
        config = self._agent_configs[name]
        agent = self._build_agent(config)
        self._agents[agent.name] = agent
        self._agent_status[name] = "deployed"
        self._persist_agent_yaml(name, config)

    def pause_agent(self, name: str) -> None:
        """Pause a deployed agent, removing it from active execution."""
        if self._agent_status.get(name) != "deployed":
            raise ValueError(f"Agent '{name}' is not deployed")
        if name in self._agents:
            del self._agents[name]
        self._agent_status[name] = "paused"

    async def update_agent(self, name: str, config: dict) -> None:
        """Update an agent's config. Pauses if deployed, resets status to draft."""
        if name not in self._agent_configs:
            raise ValueError(f"Agent '{name}' not found")
        if self._agent_status.get(name) == "deployed":
            self.pause_agent(name)
        self._agent_configs[name] = config
        self._agent_status[name] = "draft"
        self._persist_agent_yaml(name, config)

    def unregister_agent(self, name: str) -> None:
        """Remove a dynamically registered agent."""
        if name not in self._agents and name not in self._agent_configs:
            raise ValueError(f"Agent '{name}' not found")
        self._agents.pop(name, None)
        self._agent_configs.pop(name, None)
        self._agent_status.pop(name, None)
        self._remove_agent_yaml(name)

    def register_rag_pipeline(self, raw: dict) -> str:
        """Registra (o reemplaza) un RAGPipeline en el store del runtime (`_rag_specs`),
        el que usa `_resolve_rag` para el KB de un agente. Espeja `register_agent`
        pero para RAG. Devuelve el nombre registrado."""
        from astromesh.rag.loader import spec_from_raw

        spec = spec_from_raw(raw)  # valida kind + name; lanza ValueError si es inválido
        self._rag_specs[spec.name] = spec
        return spec.name


class Agent:
    def __init__(
        self,
        name,
        version,
        namespace,
        description,
        routers,
        memory,
        tools,
        pattern,
        system_prompt,
        prompt_engine,
        guardrails,
        permissions,
        orchestration_config,
        rag=None,
    ):
        self.name = name
        self.version = version
        self.namespace = namespace
        self.description = description
        self._routers = routers
        self._role_map = (orchestration_config or {}).get("role_map", {}) or {}
        self._memory = memory
        self._rag = rag
        self._tools = tools
        self._pattern = pattern
        self._system_prompt = system_prompt
        self._prompt_engine = prompt_engine
        self._guardrails = guardrails
        self._permissions = permissions
        self._orchestration_config = orchestration_config

    async def run(self, query, session_id, context=None, parent_trace_id=None, on_event=None):
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

            root_span.set_attribute("query", query_text[:5000])

            mem_span = tracing.start_span("memory_build")
            memory_context = await self._memory.build_context(
                session_id, query_text, max_tokens=4096
            )
            tracing.finish_span(mem_span)

            rag_span = tracing.start_span("rag_build")
            knowledge_context = await self._rag.build_context(query_text) if self._rag else ""
            tracing.finish_span(rag_span)

            prompt_span = tracing.start_span("prompt_render")
            rendered_prompt = self._prompt_engine.render(
                self._system_prompt,
                {**(context or {}), "memory": memory_context, "knowledge": knowledge_context},
            )
            tracing.finish_span(prompt_span)

            tool_schemas = self._tools.get_tool_schemas(self._permissions.get("allowed_actions"))
            max_iterations = self._orchestration_config.get("max_iterations", 10)
            logger.debug(
                "agent.run %s pattern=%s max_iterations=%d tools=%d query_chars=%d",
                self.name,
                self._orchestration_config.get("pattern", "react"),
                max_iterations,
                len(tool_schemas),
                len(query_text),
            )

            route_kwargs = {}
            provider_override_config = (context or {}).get("_provider_override")
            if provider_override_config:
                from astromesh.providers.factory import create_provider

                override_name = provider_override_config["name"]
                override_key = provider_override_config["key"]
                override_provider = create_provider(override_name, api_key=override_key)
                route_kwargs["provider_override"] = (override_name, override_provider)

            async def model_fn(messages, tools, role=None):
                llm_span = tracing.start_span("llm.complete", parent_span_id=root_span.span_id)
                full_messages = [{"role": "system", "content": rendered_prompt}] + messages
                resolved_role = self._role_map.get(role, role) if role else "default"
                router = self._routers.get(resolved_role) or self._routers["default"]
                llm_span.set_attribute("role", role or "default")
                llm_span.set_attribute("resolved_role", resolved_role or "default")
                try:
                    response = await router.route(full_messages, tools=tools, **route_kwargs)
                    # Fase 4.4c: attribute the outbound provider-request bytes to this agent.
                    try:
                        import json as _json
                        from astromesh.observability.metrics_export import get_manager as _gm

                        _m = _gm()
                        if _m is not None:
                            _req_bytes = len(_json.dumps(full_messages, default=str))
                            _m.record(self.name, getattr(response, "model", "unknown"), _req_bytes)
                    except Exception:
                        pass
                    if hasattr(response, "usage") and response.usage:
                        llm_span.set_attribute(
                            "input_tokens", response.usage.get("input_tokens", 0)
                        )
                        llm_span.set_attribute(
                            "output_tokens", response.usage.get("output_tokens", 0)
                        )
                    llm_span.set_attribute("model", response.model)
                    llm_span.set_attribute("provider", response.provider)
                    llm_span.set_attribute("latency_ms", response.latency_ms)
                    llm_span.set_attribute("cost", response.cost)
                    llm_span.set_attribute(
                        "tool_calls",
                        _normalize_tool_calls(response.tool_calls) if response.tool_calls else [],
                    )
                    llm_span.set_attribute("prompt", _truncate(rendered_prompt, 10_000))
                    # Store user messages so traces show the actual input
                    user_msgs = [m for m in messages if m.get("role") == "user"]
                    if user_msgs:
                        llm_span.set_attribute(
                            "input_messages",
                            _truncate(
                                "\n".join(
                                    m.get("content", "")
                                    for m in user_msgs
                                    if isinstance(m.get("content"), str)
                                ),
                                10_000,
                            ),
                        )
                    llm_span.set_attribute("response", _truncate(response.content, 10_000))
                    tracing.finish_span(llm_span)
                    if response.content:
                        _emit(on_event, {"type": "token", "content": response.content})
                    return response
                except Exception as e:
                    llm_span.set_attribute("error_message", str(e))
                    tracing.finish_span(llm_span, status=SpanStatus.ERROR)
                    raise

            async def tool_fn(name, args):
                # One id per call so a consumer can pair the result with its call.
                call_id = str(uuid.uuid4())
                _emit(
                    on_event,
                    {"type": "tool_call", "id": call_id, "name": name, "arguments": args},
                )
                tool_span = tracing.start_span(
                    "tool.call", {"tool": name}, parent_span_id=root_span.span_id
                )
                try:
                    observation = await self._tools.execute(
                        name, args, {"agent": self.name, "session": session_id}
                    )
                    tool_span.set_attribute("tool_args", args)
                    tool_span.set_attribute("tool_result", _truncate(str(observation), 5_000))
                    tracing.finish_span(tool_span)
                    _emit(on_event, {"type": "tool_result", "id": call_id, "ok": True})
                    return observation
                except Exception as e:
                    tool_span.set_attribute("error_message", str(e))
                    tracing.finish_span(tool_span, status=SpanStatus.ERROR)
                    _emit(on_event, {"type": "tool_result", "id": call_id, "ok": False})
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
            for i, step in enumerate(result.get("steps", [])):
                step_data = {
                    "iteration": i + 1,
                    "pattern": self._orchestration_config.get("pattern", "react"),
                }
                if hasattr(step, "thought") and step.thought:
                    step_data["thought"] = _truncate(step.thought, 5_000)
                if hasattr(step, "action") and step.action:
                    step_data["action"] = step.action
                    step_data["action_input"] = step.action_input or {}
                if hasattr(step, "observation") and step.observation:
                    step_data["observation"] = _truncate(step.observation, 5_000)
                if hasattr(step, "result") and step.result:
                    step_data["result"] = _truncate(step.result, 5_000)
                orch_span.add_event("orch_step", step_data)
            tracing.finish_span(orch_span)

            # Extract text for storage; keep full multimodal content in metadata.
            if isinstance(query, list):
                text_parts = [p.get("text", "") for p in query if p.get("type") == "text"]
                user_content = " ".join(text_parts)
                user_metadata = {"multimodal_content": query}
            else:
                user_content = query
                user_metadata = {}

            persist_span = tracing.start_span("memory_persist", parent_span_id=root_span.span_id)
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
            logger.debug(
                "agent.run %s finished answer_chars=%d steps=%d",
                self.name,
                len(result.get("answer", "") or ""),
                len(result.get("steps") or []),
            )
            return result

        except Exception as e:
            logger.exception("agent.run failed agent=%s session=%s", self.name, session_id)
            root_span.set_attribute("error_message", str(e))
            tracing.finish_span(root_span, status=SpanStatus.ERROR)
            raise
        finally:
            # Fase 4.3: emit the completed trace to the active collector (InternalCollector for
            # /v1/traces, or OTLPCollector when OTLP export is enabled). In `finally` so a failed run
            # (e.g. no provider) still exports the pre-LLM spans. Best-effort; never breaks the run.
            try:
                from astromesh.api.routes.traces import get_collector

                await get_collector().emit_trace(tracing)
            except Exception:
                logger.debug("trace emit failed", exc_info=True)
            # Fase 4.4c: flush the per-agent egress metric (cold gRPC needs a waited flush, like traces).
            try:
                from astromesh.observability.metrics_export import get_manager as _gm2

                _m2 = _gm2()
                if _m2 is not None:
                    _m2.record_run(tracing)  # Fase 4.3b: derive engine metrics from the span tree
                    _m2.flush()
            except Exception:
                logger.debug("agent-egress flush failed", exc_info=True)
