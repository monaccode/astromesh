"""ADK Runtime — in-process execution bridging ADK abstractions to the
Astromesh core engine (orchestration patterns + model router + providers +
tracing)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astromesh_adk.providers import parse_model_string, resolve_provider
from astromesh.core.model_router import ModelRouter
from astromesh.observability.tracing import SpanStatus, TracingContext
from astromesh.providers.base import CompletionResponse
from astromesh_adk.context import RunContext

if TYPE_CHECKING:
    pass

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
    """Placeholder — methods filled in subsequent tasks."""

    def __init__(self, provider_factory: Any = resolve_provider) -> None:
        self._provider_factory = provider_factory

    def _adk_tools_to_specs(self, tools: list | None) -> list[dict]:
        specs = []
        for t in tools or []:
            specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": getattr(t, "tool_name", getattr(t, "name", "tool")),
                        "description": getattr(t, "tool_description", getattr(t, "description", "")),
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

        async def model_fn(messages: list[dict], tools: list | None = None) -> CompletionResponse:
            full = list(messages)
            if system_prompt and not (full and full[0].get("role") == "system"):
                full = [{"role": "system", "content": system_prompt}] + full

            specs = self._adk_tools_to_specs(tools)
            span = tctx.start_span("llm.complete", {"model": primary_model})
            try:
                kwargs: dict = {}
                if specs:
                    kwargs["tools"] = specs
                resp = await router.route(
                    full, requirements={"tools": bool(specs)}, **kwargs
                )
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

    def _make_tool_fn(self, tools: list | None, tctx: "TracingContext | None" = None):
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
            except Exception:
                if span is not None and tctx is not None:
                    tctx.finish_span(span, SpanStatus.ERROR)
                raise
            if span is not None and tctx is not None:
                tctx.finish_span(span, SpanStatus.OK)
            return result

        return tool_fn

    def _build_context(
        self, agent: Any, query: str, session_id: str, context: dict | None = None
    ) -> RunContext:
        tool_names = [
            getattr(t, "tool_name", getattr(t, "name", "tool"))
            for t in getattr(agent, "tools", [])
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
