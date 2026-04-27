"""ADK Runtime — local execution implementation."""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, AsyncIterator

from astromesh_adk._internal.llm_dispatch import (
    LlmResult,
    dispatch_with_fallback,
)
from astromesh_adk.result import RunResult, StreamEvent
from astromesh_adk.team import AgentTeam as AgentTeam_

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
        async for ev in self._stream_local(agent_wrapper, query, session_id, context or {}, stream_steps, callbacks):
            yield ev

    async def _stream_local(self, a, query, session_id, context, stream_steps, callbacks):
        tools_by_name = {t.tool_name: t for t in (a.tools or [])}
        tools_schema = [
            {"name": t.tool_name, "description": t.tool_description, "input_schema": t.parameters_schema}
            for t in (a.tools or [])
        ]
        messages: list[dict] = [{"role": "user", "content": query if isinstance(query, str) else str(query)}]

        for iteration in range(a.max_iterations):
            result = await dispatch_with_fallback(
                primary_model=a.model,
                fallback_models=([a.fallback_model] if a.fallback_model else []),
                routing=a.routing,
                payload={"system": a.system_prompt, "messages": messages, "tools": tools_schema, "max_tokens": 4096},
                caller=_llm_caller,
            )

            if not result.tool_calls:
                yield StreamEvent(type="step", step={"kind": "final", "text": result.text, "model": result.model})
                yield StreamEvent(type="done", step={"answer": result.text, "model": result.model})
                return

            for tc in result.tool_calls:
                t = tools_by_name.get(tc["name"])
                out = await t(**tc["arguments"])
                yield StreamEvent(type="step", step={"kind": "tool_call", "tool": tc["name"], "args": tc["arguments"], "result": out})
                messages.append({"role": "assistant", "content": result.text or "", "tool_calls": result.tool_calls})
                messages.append({"role": "tool", "results": [{"tool_use_id": tc["id"], "content": out}]})

        raise RuntimeError(f"max_iterations={a.max_iterations} reached without final answer")

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
        previous_outputs: dict = dict(context.get("previous_outputs", {}))
        current_input = query
        agg_input_tokens = 0
        agg_output_tokens = 0
        agg_cost = 0.0
        last_answer = ""
        last_model = ""
        all_steps: list[dict] = []

        for sub in team.agents:
            ctx_with_outputs = {**context, "previous_outputs": dict(previous_outputs)}
            if isinstance(sub, AgentTeam_):
                sub_result = await self.run_team(sub, current_input, session_id, ctx_with_outputs, callbacks)
            else:
                sub_result = await self._run_local(sub, current_input, session_id, ctx_with_outputs, callbacks)
            agg_input_tokens += sub_result.tokens["input"]
            agg_output_tokens += sub_result.tokens["output"]
            agg_cost += sub_result.cost
            last_answer = sub_result.answer
            last_model = sub_result.model
            previous_outputs[sub.name] = sub_result.answer
            all_steps.append({"agent": sub.name, "answer": sub_result.answer, "steps": sub_result.steps})
            current_input = sub_result.answer

        return RunResult(
            answer=last_answer,
            steps=all_steps,
            trace=None,
            cost=agg_cost,
            tokens={"input": agg_input_tokens, "output": agg_output_tokens},
            latency_ms=0.0,
            model=last_model,
            metadata={"session_id": session_id, "previous_outputs": previous_outputs, "pattern": "pipeline"},
        )

    async def _run_parallel(self, team, query, session_id, context, callbacks):
        async def _run_one(sub):
            ctx_copy = dict(context)
            if isinstance(sub, AgentTeam_):
                return sub.name, await self.run_team(sub, query, session_id, ctx_copy, callbacks)
            return sub.name, await self._run_local(sub, query, session_id, ctx_copy, callbacks)

        results: dict = {}
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(_run_one(sub)) for sub in team.agents]

        for t in tasks:
            name, res = t.result()
            results[name] = res

        agg_input = sum(r.tokens["input"] for r in results.values())
        agg_output = sum(r.tokens["output"] for r in results.values())
        agg_cost = sum(r.cost for r in results.values())
        previous_outputs = {name: r.answer for name, r in results.items()}

        # Aggregated answer = JSON of outputs (downstream agents in pipeline parsean)
        import json
        agg_answer = json.dumps(previous_outputs, ensure_ascii=False)

        return RunResult(
            answer=agg_answer,
            steps=[{"agent": n, "answer": r.answer, "steps": r.steps} for n, r in results.items()],
            trace=None,
            cost=agg_cost,
            tokens={"input": agg_input, "output": agg_output},
            latency_ms=0.0,
            model="multi",
            metadata={"session_id": session_id, "previous_outputs": previous_outputs, "pattern": "parallel"},
        )

    async def _run_supervisor(self, team, query, session_id, context, callbacks):
        sup = team.supervisor
        if sup is None:
            raise ValueError("supervisor pattern requires team.supervisor")
        workers_by_name = {w.name: w for w in team.workers}

        worker_descriptions = "\n".join(f"- {w.name}: {w.description}" for w in team.workers)
        sup_system = (
            (sup.system_prompt or "")
            + "\n\n# Workers disponibles\n" + worker_descriptions
            + "\n\n# Tools disponibles\n"
            + "- delegate_to(worker: str, task: str) -> delega una tarea a un worker\n"
            + "- final_answer(answer: str) -> entrega la respuesta final"
        )
        delegate_schema = {
            "name": "delegate_to",
            "description": "Delega una tarea a un worker del equipo.",
            "input_schema": {
                "type": "object",
                "properties": {"worker": {"type": "string"}, "task": {"type": "string"}},
                "required": ["worker", "task"],
            },
        }
        final_schema = {
            "name": "final_answer",
            "description": "Entrega la respuesta final del equipo.",
            "input_schema": {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
        }

        messages: list[dict] = [{"role": "user", "content": query if isinstance(query, str) else str(query)}]
        worker_results: dict = {}
        agg_input = agg_output = 0
        agg_cost = 0.0
        last_model = sup.model

        for _ in range(sup.max_iterations):
            sup_res = await dispatch_with_fallback(
                primary_model=sup.model,
                fallback_models=([sup.fallback_model] if sup.fallback_model else []),
                routing=sup.routing,
                payload={"system": sup_system, "messages": messages, "tools": [delegate_schema, final_schema], "max_tokens": 4096},
                caller=_llm_caller,
            )
            agg_input += sup_res.input_tokens
            agg_output += sup_res.output_tokens
            agg_cost += sup_res.cost_usd
            last_model = sup_res.model

            if not sup_res.tool_calls:
                # Treated as final
                return RunResult(
                    answer=sup_res.text, steps=[], trace=None, cost=agg_cost,
                    tokens={"input": agg_input, "output": agg_output}, latency_ms=0.0,
                    model=last_model,
                    metadata={"session_id": session_id, "worker_results": worker_results, "pattern": "supervisor"},
                )

            tool_results = []
            for tc in sup_res.tool_calls:
                if tc["name"] == "final_answer":
                    return RunResult(
                        answer=tc["arguments"]["answer"], steps=[], trace=None, cost=agg_cost,
                        tokens={"input": agg_input, "output": agg_output}, latency_ms=0.0,
                        model=last_model,
                        metadata={"session_id": session_id, "worker_results": worker_results, "pattern": "supervisor"},
                    )
                if tc["name"] == "delegate_to":
                    worker_name = tc["arguments"]["worker"]
                    worker = workers_by_name.get(worker_name)
                    if worker is None:
                        out = {"error": f"unknown worker {worker_name!r}"}
                    else:
                        sub_res = await self._run_local(worker, tc["arguments"]["task"], session_id, dict(context), callbacks)
                        worker_results[worker_name] = sub_res.answer
                        agg_input += sub_res.tokens["input"]
                        agg_output += sub_res.tokens["output"]
                        agg_cost += sub_res.cost
                        out = sub_res.answer
                    tool_results.append({"tool_use_id": tc["id"], "content": out})

            messages.append({"role": "assistant", "content": sup_res.text or "", "tool_calls": sup_res.tool_calls})
            messages.append({"role": "tool", "results": tool_results})

        raise RuntimeError(f"supervisor max_iterations reached without final_answer")
