"""ADK Runtime — in-process execution bridging ADK abstractions to the
Astromesh core engine (orchestration patterns + model router + providers +
tracing)."""

from __future__ import annotations

import asyncio
import dataclasses
from typing import TYPE_CHECKING, Any

from astromesh_adk.providers import parse_model_string, resolve_provider
from astromesh.core.model_router import ModelRouter
from astromesh.observability.tracing import SpanStatus, TracingContext
from astromesh.providers.base import CompletionResponse
from astromesh_adk.context import RunContext
from astromesh_adk.result import RunResult, StreamEvent
from astromesh.orchestration.patterns import (
    ParallelFanOutPattern,
    PipelinePattern,
    PlanAndExecutePattern,
    ReActPattern,
)
from astromesh.orchestration.supervisor import SupervisorPattern
from astromesh.orchestration.swarm import SwarmPattern

if TYPE_CHECKING:
    pass

_PATTERNS = {
    "react": ReActPattern,
    "plan_and_execute": PlanAndExecutePattern,
    "parallel_fan_out": ParallelFanOutPattern,
    "pipeline": PipelinePattern,
}

_default_runtime: ADKRuntime | None = None


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
        self._memory_cache: dict[int, Any] = {}

    def _adk_tools_to_specs(self, tools: list | None) -> list[dict]:
        specs = []
        for t in tools or []:
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

    def _make_model_fn(self, agent: Any, tctx: TracingContext):
        primary_model = agent.model
        fallback_model = getattr(agent, "fallback_model", None)
        routing = getattr(agent, "routing", "cost_optimized")
        model_config = getattr(agent, "model_config", None)
        system_prompt = getattr(agent, "system_prompt", "") or ""

        router = ModelRouter({"strategy": routing})
        for m in [primary_model] + ([fallback_model] if fallback_model else []):
            pname, mname = _provider_and_model(m)
            provider = self._provider_factory(pname, mname, model_config)
            router.register_provider(m, provider)

        async def model_fn(
            messages: list[dict], tools: list | None = None, role: str | None = None
        ) -> CompletionResponse:
            # Core orchestration patterns (astromesh >=0.29.0) request a per-role model via
            # `role=`. The ADK binds a single ModelRouter per agent, so we accept the role for
            # signature compatibility and route through that one router regardless.
            full = list(messages)
            if system_prompt and not (full and full[0].get("role") == "system"):
                full = [{"role": "system", "content": system_prompt}] + full

            specs = self._adk_tools_to_specs(tools)
            span = tctx.start_span("llm.complete", {"model": primary_model})
            try:
                kwargs: dict = {}
                if specs:
                    kwargs["tools"] = specs
                resp = await router.route(full, requirements={"tools": bool(specs)}, **kwargs)
            except Exception:
                tctx.finish_span(span, SpanStatus.ERROR)
                raise
            usage = resp.usage or {}
            span.set_attribute("model", resp.model)
            span.set_attribute("cost", resp.cost)
            span.set_attribute("input_tokens", usage.get("input_tokens", 0))
            span.set_attribute("output_tokens", usage.get("output_tokens", 0))
            tctx.finish_span(span, SpanStatus.OK)
            return resp

        return model_fn

    def _make_tool_fn(
        self, tools: list | None, tctx: "TracingContext | None" = None, callbacks=None
    ):
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
                    except Exception:  # noqa: BLE001 — callbacks are best-effort
                        pass
                raise
            if span is not None and tctx is not None:
                tctx.finish_span(span, SpanStatus.OK)
            if callbacks is not None:
                try:
                    await callbacks.on_tool_result(name, args, result)
                except Exception:  # noqa: BLE001 — callbacks are best-effort
                    pass
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
        key = id(agent)
        mgr = self._memory_cache.get(key)
        if mgr is None:
            from astromesh.memory.factory import build_conversation_backend
            from astromesh.core.memory import MemoryManager

            backend = build_conversation_backend(conv)
            if backend is None:
                return None
            mgr = MemoryManager(
                agent_id=agent.name, config=agent.memory_config, conversation=backend
            )
            self._memory_cache[key] = mgr
        return mgr

    @staticmethod
    def _steps_to_dicts(steps: list) -> list[dict]:
        out = []
        for s in steps:
            out.append(s if isinstance(s, dict) else dataclasses.asdict(s))
        return out

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
        try:
            memory = self._get_memory(agent_wrapper)
            run_ctx = dict(context or {})
            if memory is not None:
                mctx = await memory.build_context(session_id, query)
                history_msgs = [
                    {"role": t.role, "content": t.content}
                    for t in mctx.get("conversation", [])
                ]
                if history_msgs:
                    run_ctx["_history_messages"] = history_msgs

            ctx = self._build_context(agent_wrapper, query, session_id, context)
            handler_out = await agent_wrapper._handler(ctx)
            if isinstance(handler_out, str):
                answer, steps = handler_out, []
            else:
                model_fn = self._make_model_fn(agent_wrapper, tctx)
                tool_fn = self._make_tool_fn(getattr(agent_wrapper, "tools", []), tctx, callbacks)
                pattern_cls = _PATTERNS.get(
                    getattr(agent_wrapper, "pattern", "react"), ReActPattern
                )
                pattern = pattern_cls()
                result = await pattern.execute(
                    query,
                    run_ctx,
                    model_fn,
                    tool_fn,
                    getattr(agent_wrapper, "tools", []),
                    max_iterations=getattr(agent_wrapper, "max_iterations", 10),
                )
                answer = result.get("answer", "")
                steps = result.get("steps", [])

            if memory is not None:
                from astromesh.core.memory import ConversationTurn
                from datetime import datetime, timezone

                now = datetime.now(timezone.utc)
                await memory.persist_turn(
                    session_id, ConversationTurn(role="user", content=query, timestamp=now)
                )
                await memory.persist_turn(
                    session_id, ConversationTurn(role="assistant", content=answer, timestamp=now)
                )

            tctx.finish_span(root, SpanStatus.OK)
        except Exception:
            tctx.finish_span(root, SpanStatus.ERROR)
            raise
        return RunResult.from_runtime(
            {
                "answer": answer,
                "steps": self._steps_to_dicts(steps),
                "trace": tctx.to_dict(),
            }
        )

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
            agg = self._aggregate(team.name, session_id, children)
            agg.answer = last.answer if last else ""
            return agg

        if pattern == "supervisor":
            return await self._run_supervisor(team, query, session_id, context)
        if pattern == "swarm":
            return await self._run_swarm(team, query, session_id, context)
        raise ValueError(f"unknown team pattern {pattern!r}")

    async def _run_supervisor(self, team, query, session_id, context) -> RunResult:
        supervisor = team.supervisor
        workers = {w.name: w for w in team.workers}
        tctx = TracingContext(supervisor.name, session_id)
        root = tctx.start_span("agent.run", {"agent": supervisor.name})
        model_fn = self._make_model_fn(supervisor, tctx)

        async def delegating_tool_fn(name: str, args: dict):
            if name in workers:
                r = await self.run_agent(
                    workers[name], args.get("query", query), session_id, context
                )
                return r.answer
            raise KeyError(f"worker {name!r} not found")

        pattern = SupervisorPattern(team._build_workers_dict())
        try:
            result = await pattern.execute(
                query,
                context or {},
                model_fn,
                delegating_tool_fn,
                [],
                max_iterations=getattr(supervisor, "max_iterations", 10),
            )
            tctx.finish_span(root, SpanStatus.OK)
        except Exception:
            tctx.finish_span(root, SpanStatus.ERROR)
            raise
        return RunResult.from_runtime(
            {
                "answer": result.get("answer", ""),
                "steps": self._steps_to_dicts(result.get("steps", [])),
                "trace": tctx.to_dict(),
            }
        )

    async def _run_swarm(self, team, query, session_id, context) -> RunResult:
        agents = {a.name: a for a in team.agents}
        entry = team.entry_agent or team.agents[0]
        tctx = TracingContext(entry.name, session_id)
        root = tctx.start_span("agent.run", {"agent": entry.name})
        model_fn = self._make_model_fn(entry, tctx)

        async def handoff_tool_fn(name: str, args: dict):
            if name in agents:
                r = await self.run_agent(
                    agents[name], args.get("query", query), session_id, context
                )
                return r.answer
            raise KeyError(f"agent {name!r} not found")

        pattern = SwarmPattern(team._build_agent_configs())
        try:
            result = await pattern.execute(
                query,
                context or {},
                model_fn,
                handoff_tool_fn,
                [],
                max_iterations=getattr(entry, "max_iterations", 10),
            )
            tctx.finish_span(root, SpanStatus.OK)
        except Exception:
            tctx.finish_span(root, SpanStatus.ERROR)
            raise
        return RunResult.from_runtime(
            {
                "answer": result.get("answer", ""),
                "steps": self._steps_to_dicts(result.get("steps", [])),
                "trace": tctx.to_dict(),
            }
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

    async def __aenter__(self) -> ADKRuntime:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        await self.shutdown()
        return False
