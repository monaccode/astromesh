# astromesh/workflow/executor.py
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from jinja2 import Environment, BaseLoader, Undefined

from astromesh.workflow.models import StepSpec, StepResult, StepStatus, StepType


class _SilentUndefined(Undefined):
    def __str__(self):
        return ""

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return False


class StepExecutor:
    """Dispatches individual workflow steps: agent, tool, or switch."""

    def __init__(self, runtime, tool_registry):
        self._runtime = runtime
        self._tool_registry = tool_registry
        self._jinja = Environment(loader=BaseLoader(), undefined=_SilentUndefined)

    async def execute_step(self, step: StepSpec, context: dict[str, Any]) -> StepResult:
        """Execute a single step with retry and timeout handling."""
        max_attempts = step.retry.max_attempts if step.retry else 1
        backoff = step.retry.backoff if step.retry else "fixed"
        delay = step.retry.initial_delay_seconds if step.retry else 1.0

        last_error: str | None = None
        for attempt in range(max_attempts):
            try:
                coro = self._dispatch(step, context)
                if step.timeout_seconds:
                    result = await asyncio.wait_for(coro, timeout=step.timeout_seconds)
                else:
                    result = await coro
                return result
            except asyncio.TimeoutError:
                last_error = f"Step '{step.name}' timed out after {step.timeout_seconds}s"
            except Exception as exc:
                last_error = str(exc)

            if attempt < max_attempts - 1:
                sleep_time = delay * (2**attempt if backoff == "exponential" else 1)
                await asyncio.sleep(sleep_time)

        return StepResult(name=step.name, status=StepStatus.ERROR, error=last_error)

    async def _dispatch(self, step: StepSpec, context: dict[str, Any]) -> StepResult:
        start = time.time()
        if step.step_type == StepType.AGENT:
            return await self._run_agent(step, context, start)
        elif step.step_type == StepType.TOOL:
            return await self._run_tool(step, context, start)
        elif step.step_type == StepType.SWITCH:
            return await self._run_switch(step, context, start)
        raise ValueError(f"Unknown step type for step '{step.name}'")

    async def _run_agent(self, step: StepSpec, ctx: dict, start: float) -> StepResult:
        rendered_input = self._render(step.input_template or "", ctx)
        session_id = str(uuid.uuid4())
        result = await self._runtime.run(step.agent, rendered_input, session_id=session_id)
        elapsed = (time.time() - start) * 1000
        return StepResult(
            name=step.name, status=StepStatus.SUCCESS, output=result, duration_ms=elapsed
        )

    async def _run_tool(self, step: StepSpec, ctx: dict, start: float) -> StepResult:
        arguments = {}
        for key, val in (step.arguments or {}).items():
            if isinstance(val, str):
                arguments[key] = self._render(val, ctx)
            else:
                arguments[key] = val
        result = await self._tool_registry.execute(step.tool, arguments)
        elapsed = (time.time() - start) * 1000
        return StepResult(
            name=step.name, status=StepStatus.SUCCESS, output=result, duration_ms=elapsed
        )

    async def _run_switch(self, step: StepSpec, ctx: dict, start: float) -> StepResult:
        goto: str | None = None
        for branch in step.switch:
            if branch.get("default"):
                goto = branch["goto"]
                break
            condition = branch.get("when", "")
            rendered = self._render(condition, ctx).strip()
            if rendered.lower() in ("true", "1", "yes"):
                goto = branch["goto"]
                break
        elapsed = (time.time() - start) * 1000
        return StepResult(
            name=step.name, status=StepStatus.SUCCESS, output={"goto": goto}, duration_ms=elapsed
        )

    def _render(self, template_str: str, context: dict) -> str:
        return self._jinja.from_string(template_str).render(**context)
