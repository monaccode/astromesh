"""ADK Runtime — in-process execution bridging ADK abstractions to the
Astromesh core engine (orchestration patterns + model router + providers +
tracing)."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import weakref
from datetime import UTC
from typing import Any, Self

from astromesh.core.guardrails import GuardrailBlocked, GuardrailsEngine
from astromesh.core.model_router import ModelRouter
from astromesh.core.tokens import estimate_tokens, resolve_context_window
from astromesh.errors import AgentConfigError
from astromesh.observability.tracing import SpanStatus, TracingContext
from astromesh.orchestration.observaciones import DEFAULT_MAX_TOOL_RESULT_TOKENS
from astromesh.orchestration.patterns import (
    ParallelFanOutPattern,
    PipelinePattern,
    PlanAndExecutePattern,
    ReActPattern,
)
from astromesh.orchestration.supervisor import SupervisorPattern
from astromesh.orchestration.swarm import SwarmPattern
from astromesh.providers.base import CompletionResponse

from astromesh_adk.context import RunContext
from astromesh_adk.providers import parse_model_string, resolve_provider
from astromesh_adk.result import RunResult, StreamEvent

# Core's patterns the ADK can build for a single agent. `swarm` and `glyph` are left out:
# swarm is a team pattern here (AgentTeam), glyph needs a compiled program.
PATTERNS = {
    "react": ReActPattern,
    "plan_and_execute": PlanAndExecutePattern,
    "parallel_fan_out": ParallelFanOutPattern,
    "pipeline": PipelinePattern,
    "supervisor": SupervisorPattern,
}
_BLOCKED = "[blocked by guardrail]"  # same marker core's engine puts on filtered steps
_RESPONSE_TOKENS = 1024  # core's DEFAULT_RESPONSE_TOKENS, when the model sets no max_tokens


def _tool_name(t: Any) -> str:
    return getattr(t, "tool_name", getattr(t, "name", "tool"))


def _build_pattern(agent: Any):
    """Like core's `AgentRuntime._build_pattern`: unknown patterns raise, never fall back."""
    name = getattr(agent, "pattern", "react") or "react"
    if name not in PATTERNS:
        raise AgentConfigError(
            f"pattern {name!r} does not exist; valid: {', '.join(sorted(PATTERNS))}"
        )
    if name == "supervisor":
        workers = [_tool_name(t) for t in agent.tools if getattr(t, "is_agent_tool", False)]
        if not workers:
            raise AgentConfigError(
                "pattern 'supervisor' needs at least one agent tool (other_agent.as_tool()): "
                "they are its workers"
            )
        return SupervisorPattern(workers=workers)
    if name == "pipeline":
        return PipelinePattern(stages=getattr(agent, "stages", None))
    return PATTERNS[name]()


_default_runtime: ADKRuntime | None = None

logger = logging.getLogger(__name__)


def _provider_and_model(model: str) -> tuple[str, str]:
    """Map a model id to (provider_name, model_name).

    Bare Clarus model ids (e.g. 'claude-haiku-4-5', 'gpt-4o-mini') have no
    'provider/' prefix; parse_model_string would wrongly default them all to
    openai, so we route by family first.
    """
    if "/" in model:
        return parse_model_string(model)
    if model.startswith("claude"):
        return "anthropic", model
    if model.startswith(("gpt", "o1", "o3", "o4", "chatgpt")):
        return "openai", model
    return parse_model_string(model)


def get_or_create_runtime() -> ADKRuntime:
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = ADKRuntime()
    return _default_runtime


def set_runtime(rt: ADKRuntime | None) -> None:
    """Test hook: override the process-wide runtime singleton."""
    global _default_runtime
    _default_runtime = rt


class ADKRuntime:
    """In-process runtime: executes ADK agents/teams via the Astromesh core
    engine (orchestration patterns, ModelRouter, providers) and emits a
    RunResult with cost/token/latency accounting from the tracing context."""

    def __init__(self, provider_factory: Any = resolve_provider) -> None:
        self._provider_factory = provider_factory
        self._memory_cache: weakref.WeakKeyDictionary[Any, Any] = weakref.WeakKeyDictionary()

    def _adk_tools_to_specs(self, tools: list | None) -> list[dict]:
        specs = []
        for t in tools or []:
            if isinstance(t, dict):  # already a function-calling spec
                specs.append(t)
                continue
            specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": getattr(t, "tool_name", getattr(t, "name", "tool")),
                        "description": getattr(
                            t, "tool_description", getattr(t, "description", "")
                        ),
                        "parameters": getattr(t, "parameters_schema", {}) or {},
                    },
                }
            )
        return specs

    def _router(self, models: list[str], routing: str, model_config: dict | None) -> ModelRouter:
        router = ModelRouter({"strategy": routing})
        for m in models:
            pname, mname = _provider_and_model(m)
            router.register_provider(m, self._provider_factory(pname, mname, model_config))
        return router

    def _make_model_fn(self, agent: Any, tctx: TracingContext, guard: dict | None = None):
        """`guard` = {"engine": GuardrailsEngine, "counted": int, "cut": GuardrailBlocked|None}:
        `cost_limit` is checked before each call, like core's engine."""
        primary_model = agent.model
        fallback_model = getattr(agent, "fallback_model", None)
        routing = getattr(agent, "routing", "cost_optimized")
        model_config = getattr(agent, "model_config", None)
        system_prompt = getattr(agent, "system_prompt", "") or ""

        default = [primary_model] + ([fallback_model] if fallback_model else [])
        routers = {"default": (self._router(default, routing, model_config), primary_model)}
        for role, m in (getattr(agent, "roles", None) or {}).items():
            routers[role] = (self._router([m], routing, model_config), m)

        async def model_fn(
            messages: list[dict], tools: list | None = None, role: str | None = None
        ) -> CompletionResponse:
            # Core patterns ask for a per-role model via `role=`; an unmapped role uses
            # the agent's model (core: `self._routers.get(role) or self._routers["default"]`).
            if guard is not None:
                try:
                    guard["engine"].check_budget(guard["counted"])
                except GuardrailBlocked as blocked:
                    guard["cut"] = guard["cut"] or blocked
                    raise guard["cut"] from None
            router, model_name = routers.get(role) or routers["default"]
            full = list(messages)
            if system_prompt and not (full and full[0].get("role") == "system"):
                full = [{"role": "system", "content": system_prompt}] + full

            specs = self._adk_tools_to_specs(tools)
            span = tctx.start_span("llm.complete", {"model": model_name, "role": role or "default"})
            try:
                kwargs: dict = {}
                if specs:
                    kwargs["tools"] = specs
                resp = await router.route(full, requirements={"tools": bool(specs)}, **kwargs)
            except Exception:
                tctx.finish_span(span, SpanStatus.ERROR)
                raise
            usage = resp.usage or {}
            if guard is not None:
                guard["counted"] += guard["engine"].tokens_of(usage)
            span.set_attribute("model", resp.model)
            span.set_attribute("provider", resp.provider)
            span.set_attribute("cost", resp.cost)
            span.set_attribute("input_tokens", usage.get("input_tokens", 0))
            span.set_attribute("output_tokens", usage.get("output_tokens", 0))
            # Same attribute core's engine writes; `usage_from_trace` reads it as tokens_cached.
            span.set_attribute("cached_tokens", usage.get("cache_read_input_tokens", 0))
            tctx.finish_span(span, SpanStatus.OK)
            return resp

        return model_fn

    def _make_tool_fn(self, tools: list | None, tctx: TracingContext | None = None, callbacks=None):
        index = {}
        for t in tools or []:
            name = getattr(t, "tool_name", getattr(t, "name", None))
            if name:
                index[name] = t

        async def tool_fn(name: str, args: dict) -> Any:
            if name not in index:
                raise KeyError(f"tool {name!r} not registered")
            t = index[name]
            span = tctx.start_span("tool.call", {"tool": name}) if tctx else None
            try:
                if hasattr(t, "execute"):
                    result = await t.execute(args)
                else:
                    result = await t(**(args or {}))
            except Exception as exc:
                if span is not None and tctx is not None:
                    tctx.finish_span(span, SpanStatus.ERROR)
                if callbacks is not None:
                    try:
                        await callbacks.on_error(exc, {"tool": name})
                    except Exception:  # callbacks are best-effort
                        logger.debug("callbacks.on_error failed", exc_info=True)
                raise
            if span is not None and tctx is not None:
                tctx.finish_span(span, SpanStatus.OK)
            if callbacks is not None:
                try:
                    await callbacks.on_tool_result(name, args, result)
                except Exception:  # callbacks are best-effort
                    logger.debug("callbacks.on_tool_result failed", exc_info=True)
            return result

        return tool_fn

    def _build_context(
        self, agent: Any, query: str, session_id: str, context: dict | None = None
    ) -> RunContext:
        tool_names = [
            getattr(t, "tool_name", getattr(t, "name", "tool")) for t in getattr(agent, "tools", [])
        ]
        ctx = RunContext.from_run_params(
            query=query,
            session_id=session_id,
            agent_name=agent.name,
            context=context,
            tool_names=tool_names,
        )
        tool_fn = self._make_tool_fn(getattr(agent, "tools", []))

        async def _complete(q: str, **kw) -> str:
            from astromesh.observability.tracing import TracingContext as _TC

            tctx = _TC(agent.name, session_id)
            mf = self._make_model_fn(agent, tctx)
            resp = await mf([{"role": "user", "content": q}], None)
            return resp.content

        ctx._call_tool_fn = tool_fn
        ctx._complete_fn = _complete
        return ctx

    def _get_memory(self, agent: Any):
        conv = (getattr(agent, "memory_config", {}) or {}).get("conversational")
        if not conv or not conv.get("backend"):
            return None
        mgr = self._memory_cache.get(agent)
        if mgr is None:
            from astromesh.core.memory import MemoryManager
            from astromesh.memory.factory import build_conversation_backend

            backend = build_conversation_backend(conv)
            if backend is None:
                return None
            mgr = MemoryManager(
                agent_id=agent.name, config=agent.memory_config, conversation=backend
            )
            self._memory_cache[agent] = mgr
        return mgr

    @staticmethod
    def _steps_to_dicts(steps: list) -> list[dict]:
        out = []
        for s in steps:
            out.append(s if isinstance(s, dict) else dataclasses.asdict(s))
        return out

    @staticmethod
    async def _persist(memory, agent_name: str, session_id: str, query: str, answer: str):
        from datetime import datetime

        from astromesh.core.memory import ConversationTurn

        now = datetime.now(UTC)
        try:
            await memory.persist_turn(
                session_id, ConversationTurn(role="user", content=query, timestamp=now)
            )
            await memory.persist_turn(
                session_id, ConversationTurn(role="assistant", content=answer, timestamp=now)
            )
        except Exception:
            logger.warning(
                "memory.persist_turn failed for agent=%s session=%s; "
                "returning answer without persisting this turn",
                agent_name,
                session_id,
                exc_info=True,
            )

    def _history_budget(self, agent: Any, specs: list[dict]) -> int | None:
        """Tokens left for history, as core's engine sizes it; None if the window is unknown."""
        declared = getattr(agent, "context_window", None)
        models = [agent.model] + ([agent.fallback_model] if agent.fallback_model else [])
        candidates = []
        for m in models:
            pname, mname = _provider_and_model(m)
            candidates.append({"provider": pname, "model": mname, "context_window": declared})
        window, source = resolve_context_window(candidates)
        if source == "default":
            return None
        base = (
            estimate_tokens(getattr(agent, "system_prompt", "") or "")
            + estimate_tokens(json.dumps(specs, default=str))
            + int(
                (getattr(agent, "model_config", None) or {}).get("max_tokens") or _RESPONSE_TOKENS
            )
        )
        return max(0, int(window * 0.9) - base)

    @staticmethod
    def _tool_budget(agent: Any) -> dict:
        """The `_presupuesto_tools` core patterns read (`presupuesto_de`)."""
        return {
            "default": getattr(agent, "max_tool_result_tokens", None)
            or DEFAULT_MAX_TOOL_RESULT_TOKENS,
            "por_tool": {
                _tool_name(t): t.max_result_tokens
                for t in getattr(agent, "tools", [])
                if getattr(t, "max_result_tokens", None)
            },
        }

    async def run_agent(
        self,
        agent_wrapper: Any,
        query: str,
        session_id: str = "default",
        context: dict | None = None,
        callbacks: Any = None,
    ) -> RunResult:
        tctx = TracingContext(agent_wrapper.name, session_id)
        root = tctx.start_span("agent.run", {"agent": agent_wrapper.name})
        engine = GuardrailsEngine(
            getattr(agent_wrapper, "guardrails_config", None), agent_name=agent_wrapper.name
        )
        guard = {"engine": engine, "counted": 0, "cut": None}
        memory = self._get_memory(agent_wrapper)
        tools = getattr(agent_wrapper, "tools", [])
        try:
            # Input rules run before memory and the model, so both see the filtered text.
            if engine.has_input:
                query = engine.check_input(query).text
            run_ctx = dict(context or {})
            run_ctx["_presupuesto_tools"] = self._tool_budget(agent_wrapper)
            specs = self._adk_tools_to_specs(tools)
            if memory is not None:
                try:
                    mctx = await memory.build_context(session_id, query)
                except Exception:
                    logger.warning(
                        "memory.build_context failed for agent=%s session=%s; "
                        "proceeding without injected history",
                        agent_wrapper.name,
                        session_id,
                        exc_info=True,
                    )
                    mctx = {}
                if mctx:
                    memory.fit_history(mctx, self._history_budget(agent_wrapper, specs))
                history_msgs = [
                    {"role": t.role, "content": t.content} for t in mctx.get("conversation", [])
                ]
                if history_msgs:
                    run_ctx["_history_messages"] = history_msgs

            ctx = self._build_context(agent_wrapper, query, session_id, context)
            handler_out = await agent_wrapper._handler(ctx)
            if isinstance(handler_out, str):
                answer, steps = handler_out, []
            else:
                model_fn = self._make_model_fn(agent_wrapper, tctx, guard)
                tool_fn = self._make_tool_fn(tools, tctx, callbacks)
                result = await self._execute(
                    _build_pattern(agent_wrapper),
                    query,
                    run_ctx,
                    model_fn,
                    tool_fn,
                    specs,
                    getattr(agent_wrapper, "max_iterations", 10),
                    guard,
                )
                answer = result.get("answer", "")
                steps = result.get("steps", [])
            answer, steps = self._filter_output(engine, answer, self._steps_to_dicts(steps))

            if memory is not None:
                await self._persist(memory, agent_wrapper.name, session_id, query, answer)
            tctx.finish_span(root, SpanStatus.OK)
        except GuardrailBlocked as blocked:
            # A block is an answer, not an error (core 0.70): blocked input never enters
            # the history; any other block stores the (filtered) query and the refusal.
            if memory is not None and blocked.direction != "input":
                await self._persist(memory, agent_wrapper.name, session_id, query, blocked.message)
            return self._blocked_result(tctx, root, blocked)
        except Exception:
            tctx.finish_span(root, SpanStatus.ERROR)
            raise
        return RunResult.from_runtime({"answer": answer, "steps": steps, "trace": tctx.to_dict()})

    @staticmethod
    async def _execute(pattern, query, run_ctx, model_fn, tool_fn, specs, max_iterations, guard):
        try:
            result = await pattern.execute(
                query, run_ctx, model_fn, tool_fn, specs, max_iterations=max_iterations
            )
        except GuardrailBlocked:
            raise
        except Exception:
            # A pattern that wraps the budget error in its own is still a refusal.
            if guard["cut"] is not None:
                raise guard["cut"] from None
            raise
        if guard["cut"] is not None:
            raise guard["cut"]
        return result

    @staticmethod
    def _filter_output(engine: GuardrailsEngine, answer: Any, steps: list[dict]):
        """Output rules on the answer and on the steps (they travel in the result too)."""
        if not engine.has_output:
            return answer, steps
        for step in steps:
            for key in ("thought", "observation", "result"):
                if isinstance(step.get(key), str) and step[key]:
                    filtered = engine.filter_stream(step[key])
                    step[key] = _BLOCKED if filtered is None else filtered
        text = answer if isinstance(answer, str) else str(answer)
        return engine.check_output(text).text, steps

    @staticmethod
    def _blocked_result(tctx: TracingContext, root, blocked: GuardrailBlocked) -> RunResult:
        root.set_attribute("guardrail.blocked", True)
        root.set_attribute("guardrail.rule", blocked.rule)
        tctx.finish_span(root, SpanStatus.OK)
        return RunResult.from_runtime(
            {
                "answer": blocked.message,
                "steps": [],
                "trace": tctx.to_dict(),
                "blocked": True,
                "guardrail": blocked.as_dict(),
            }
        )

    async def _run_lead(self, lead, query, session_id, context, pattern, tool_fn, specs):
        """A team pattern under its lead agent's guardrails (supervisor / swarm entry), the way
        core runs a chain: the lead's rules filter the team's input and output, its
        `cost_limit` budgets the lead's model calls, and a block is the team's answer."""
        tctx = TracingContext(lead.name, session_id)
        root = tctx.start_span("agent.run", {"agent": lead.name})
        engine = GuardrailsEngine(getattr(lead, "guardrails_config", None), agent_name=lead.name)
        guard = {"engine": engine, "counted": 0, "cut": None}
        try:
            if engine.has_input:
                query = engine.check_input(query).text
            result = await self._execute(
                pattern,
                query,
                dict(context or {}),
                self._make_model_fn(lead, tctx, guard),
                tool_fn,
                specs,
                getattr(lead, "max_iterations", 10),
                guard,
            )
            answer, steps = self._filter_output(
                engine, result.get("answer", ""), self._steps_to_dicts(result.get("steps", []))
            )
            tctx.finish_span(root, SpanStatus.OK)
        except GuardrailBlocked as blocked:
            return self._blocked_result(tctx, root, blocked)
        except Exception:
            tctx.finish_span(root, SpanStatus.ERROR)
            raise
        return RunResult.from_runtime({"answer": answer, "steps": steps, "trace": tctx.to_dict()})

    @staticmethod
    def _is_team(obj: Any) -> bool:
        return hasattr(obj, "pattern") and hasattr(obj, "agents") and not hasattr(obj, "_handler")

    async def _run_member(self, member: Any, query: str, session_id: str, context, callbacks=None):
        if self._is_team(member):
            return await self.run_team(member, query, session_id, context, callbacks)
        return await self.run_agent(member, query, session_id, context, callbacks)

    def _aggregate(
        self, name: str, session_id: str, children: list[tuple[str, RunResult]]
    ) -> RunResult:
        spans: list = []
        steps: list = []
        cost = 0.0
        tin = tout = 0
        latency = 0.0
        parts = []
        blocked = next((r for _, r in children if r.blocked), None)
        for agent_name, r in children:
            cost += r.cost
            tin += r.tokens.get("input", 0)
            tout += r.tokens.get("output", 0)
            latency = max(latency, r.latency_ms)
            parts.append(f"## {agent_name}\n{r.answer}")
            steps.append({"agent": agent_name, "answer": r.answer, "steps": r.steps})
            if r.trace and r.trace.get("spans"):
                spans.extend(r.trace["spans"])
        return RunResult(
            answer="\n\n".join(parts),
            steps=steps,
            trace={
                "trace_id": session_id,
                "agent": name,
                "session_id": session_id,
                "is_sampled": True,
                "spans": spans,
            },
            cost=cost,
            tokens={"input": tin, "output": tout},
            latency_ms=latency,
            model="multi",
            blocked=blocked is not None,
            guardrail=blocked.guardrail if blocked is not None else None,
        )

    async def run_team(
        self,
        team: Any,
        query: str,
        session_id: str = "default",
        context: dict | None = None,
        callbacks: Any = None,
    ) -> RunResult:
        pattern = team.pattern
        members = team.agents

        if pattern == "parallel":
            results = await asyncio.gather(
                *[self._run_member(m, query, session_id, context, callbacks) for m in members]
            )
            named = [
                (m.name if hasattr(m, "name") else f"member{i}", r)
                for i, (m, r) in enumerate(zip(members, results))
            ]
            return self._aggregate(team.name, session_id, named)

        if pattern == "pipeline":
            current = query
            children: list[tuple[str, RunResult]] = []
            last: RunResult | None = None
            for i, m in enumerate(members):
                r = await self._run_member(m, current, session_id, context, callbacks)
                children.append((getattr(m, "name", f"stage{i}"), r))
                current = r.answer
                last = r
                if r.blocked:  # a refusal is not the next stage's query
                    break
            agg = self._aggregate(team.name, session_id, children)
            agg.answer = last.answer if last else ""
            return agg

        if pattern == "supervisor":
            return await self._run_supervisor(team, query, session_id, context)
        if pattern == "swarm":
            return await self._run_swarm(team, query, session_id, context)
        raise ValueError(f"unknown team pattern {pattern!r}")

    async def _run_supervisor(self, team, query, session_id, context) -> RunResult:
        workers = {w.name: w for w in team.workers}

        async def delegating_tool_fn(name: str, args: dict):
            if name in workers:
                r = await self.run_agent(
                    workers[name], args.get("query", query), session_id, context
                )
                return r.answer
            raise KeyError(f"worker {name!r} not found")

        return await self._run_lead(
            team.supervisor,
            query,
            session_id,
            context,
            SupervisorPattern(list(workers)),
            delegating_tool_fn,
            self._adk_tools_to_specs([w.as_tool() for w in team.workers]),
        )

    async def _run_swarm(self, team, query, session_id, context) -> RunResult:
        agents = {a.name: a for a in team.agents}

        async def handoff_tool_fn(name: str, args: dict):
            # core >=0.71: the handoff is a tool call and the member's answer is final;
            # `args["query"]` already carries the conversation.
            if name in agents:
                r = await self.run_agent(
                    agents[name], args.get("query", query), session_id, context
                )
                return {"answer": r.answer}
            raise KeyError(f"agent {name!r} not found")

        return await self._run_lead(
            team.entry_agent or team.agents[0],
            query,
            session_id,
            context,
            SwarmPattern(workers=list(agents)),
            handoff_tool_fn,
            self._adk_tools_to_specs([a.as_tool() for a in team.agents]),
        )

    async def stream_agent(
        self,
        agent_wrapper,
        query,
        session_id="default",
        context=None,
        stream_steps=False,
        callbacks=None,
    ):
        result = await self.run_agent(agent_wrapper, query, session_id, context, callbacks)
        if stream_steps:
            for s in result.steps:
                yield StreamEvent(type="step", step=s)
        yield StreamEvent(type="done", result=result)

    async def run_class_agent(
        self,
        agent_instance,
        query,
        session_id="default",
        context=None,
        callbacks=None,
    ) -> RunResult:
        ctx = self._build_context(agent_instance, query, session_id, context)
        await agent_instance.on_before_run(ctx)
        if not hasattr(agent_instance, "_handler"):

            async def _noop(c):
                return None

            agent_instance._handler = _noop  # type: ignore[attr-defined]
        result = await self.run_agent(agent_instance, query, session_id, context, callbacks)
        await agent_instance.on_after_run(ctx, result)
        return result

    async def stream_class_agent(
        self,
        agent_instance,
        query,
        session_id="default",
        context=None,
        stream_steps=False,
        callbacks=None,
    ):
        result = await self.run_class_agent(agent_instance, query, session_id, context, callbacks)
        if stream_steps:
            for s in result.steps:
                yield StreamEvent(type="step", step=s)
        yield StreamEvent(type="done", result=result)

    async def start(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        await self.shutdown()
        return False
