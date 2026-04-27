"""ADK Runtime — local execution implementation."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, AsyncIterator

from astromesh_adk._internal.llm_dispatch import (
    LlmResult,
    dispatch_with_fallback,
)
from astromesh_adk.result import RunResult, StreamEvent

if TYPE_CHECKING:
    from astromesh_adk.agent import AgentWrapper
    from astromesh_adk.team import AgentTeam


_default_runtime = None


def get_or_create_runtime():
    """Get or lazily create the default ADKRuntime."""
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = ADKRuntime()
    return _default_runtime


async def _llm_caller(model: str, payload: dict) -> LlmResult:
    """Default LLM caller. Tests monkeypatch this symbol.

    In production, downstream consumers (e.g. agents-clarus) replace this via
    `runner._llm_caller = my_provider_dispatch` at module init.
    """
    raise RuntimeError(
        "No LLM caller configured. Set astromesh_adk.runner._llm_caller "
        "to an async callable (model, payload) -> LlmResult."
    )


class ADKRuntime:
    """Local in-process execution of agents and teams."""

    async def start(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.shutdown()
        return False

    async def run_agent(
        self,
        agent_wrapper: "AgentWrapper",
        query,
        session_id: str = "default",
        context: dict | None = None,
        callbacks=None,
    ) -> RunResult:
        return await self._run_local(agent_wrapper, query, session_id, context or {}, callbacks)

    async def _run_local(
        self,
        a: "AgentWrapper",
        query,
        session_id: str,
        context: dict,
        callbacks,
    ) -> RunResult:
        t0 = time.perf_counter()
        steps: list[dict] = []
        tools_by_name = {t.tool_name: t for t in (a.tools or [])}
        tools_schema = [
            {"name": t.tool_name, "description": t.tool_description, "input_schema": t.parameters_schema}
            for t in (a.tools or [])
        ]
        messages: list[dict] = [{"role": "user", "content": query if isinstance(query, str) else str(query)}]

        total_input = 0
        total_output = 0
        total_cost = 0.0
        last_model = a.model

        for iteration in range(a.max_iterations):
            result = await dispatch_with_fallback(
                primary_model=a.model,
                fallback_models=([a.fallback_model] if a.fallback_model else []),
                routing=a.routing,
                payload={
                    "system": a.system_prompt,
                    "messages": messages,
                    "tools": tools_schema,
                    "max_tokens": 4096,
                },
                caller=_llm_caller,
            )
            total_input += result.input_tokens
            total_output += result.output_tokens
            total_cost += result.cost_usd
            last_model = result.model

            if not result.tool_calls:
                steps.append({"kind": "final", "text": result.text})
                latency_ms = (time.perf_counter() - t0) * 1000
                return RunResult(
                    answer=result.text,
                    steps=steps,
                    trace=None,
                    cost=total_cost,
                    tokens={"input": total_input, "output": total_output},
                    latency_ms=latency_ms,
                    model=last_model,
                    metadata={"session_id": session_id, "iterations": iteration + 1},
                )

            # Execute tool calls
            tool_results = []
            for tc in result.tool_calls:
                t = tools_by_name.get(tc["name"])
                if t is None:
                    out = {"error": f"unknown tool {tc['name']!r}"}
                else:
                    out = await t(**tc["arguments"])
                steps.append({"kind": "tool_call", "tool": tc["name"], "args": tc["arguments"], "result": out})
                tool_results.append({"tool_use_id": tc["id"], "content": out})

            messages.append({"role": "assistant", "content": result.text or "", "tool_calls": result.tool_calls})
            messages.append({"role": "tool", "results": tool_results})

        raise RuntimeError(f"max_iterations={a.max_iterations} reached without final answer")

    async def stream_agent(self, agent_wrapper, query, session_id="default", context=None, stream_steps=False, callbacks=None):
        result = await self.run_agent(agent_wrapper, query, session_id, context, callbacks)
        yield StreamEvent(type="done", step={"answer": result.answer, "model": result.model})

    async def run_class_agent(self, *args, **kwargs):
        raise NotImplementedError("run_class_agent not in MVP; pending future task")

    async def stream_class_agent(self, *args, **kwargs):
        raise NotImplementedError("stream_class_agent not in MVP; pending future task")
        yield  # generator stub

    async def run_team(self, team: "AgentTeam", query, session_id="default", context=None, callbacks=None) -> RunResult:
        ctx = context or {}
        if team.pattern == "pipeline":
            return await self._run_pipeline(team, query, session_id, ctx, callbacks)
        if team.pattern == "parallel":
            return await self._run_parallel(team, query, session_id, ctx, callbacks)
        if team.pattern == "supervisor":
            return await self._run_supervisor(team, query, session_id, ctx, callbacks)
        raise NotImplementedError(f"team.pattern={team.pattern!r} not supported in 0.1.7 MVP")

    async def _run_pipeline(self, team, query, session_id, context, callbacks):
        raise NotImplementedError  # filled in Task A6

    async def _run_parallel(self, team, query, session_id, context, callbacks):
        raise NotImplementedError  # filled in Task A7

    async def _run_supervisor(self, team, query, session_id, context, callbacks):
        raise NotImplementedError  # filled in Task A8
