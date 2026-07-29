# astromesh/workflow/executor.py
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from jinja2 import BaseLoader, Environment, StrictUndefined, Undefined
from jinja2.exceptions import UndefinedError

from astromesh.workflow.models import StepResult, StepSpec, StepStatus, StepType


class _SilentUndefined(Undefined):
    def __str__(self):
        return ""

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return False


class StepExecutor:
    """Dispatches individual workflow steps: agent, tool, or switch."""

    def __init__(self, runtime, tool_registry, parent_trace_id=None, session_id=None):
        self._runtime = runtime
        self._tool_registry = tool_registry
        self._jinja = Environment(loader=BaseLoader(), undefined=_SilentUndefined)
        # Entorno estricto para las guardas que lo pidan: un `when` con un campo
        # inexistente tiene que gritar, no rendir vacío y saltear en silencio.
        self._jinja_strict = Environment(loader=BaseLoader(), undefined=StrictUndefined)
        # Hasta acá cada paso `agent` abría su propia sesión y su propio árbol de
        # trazas, así que un workflow se veía en el timeline como N corridas sueltas
        # sin relación entre sí.
        self._parent_trace_id = parent_trace_id
        self._session_id = session_id

    def bind(self, parent_trace_id, session_id) -> StepExecutor:
        """Devuelve un executor igual a este pero atado al trace y la sesión de una
        corrida. `_drive` lo llama por run; los stubs de test que no lo implementan
        se usan tal cual."""
        return StepExecutor(
            runtime=self._runtime,
            tool_registry=self._tool_registry,
            parent_trace_id=parent_trace_id,
            session_id=session_id,
        )

    async def execute_step(self, step: StepSpec, context: dict[str, Any]) -> StepResult:
        """Execute a single step with retry and timeout handling."""
        if step.when is not None:
            try:
                matched = self._eval_condition(step.when, context, step.strict_conditions)
            except UndefinedError as exc:
                return StepResult(
                    name=step.name,
                    status=StepStatus.ERROR,
                    error=f"condición inválida en el paso '{step.name}': {exc}",
                    condition_matched=False,
                )
            if not matched:
                return StepResult(
                    name=step.name, status=StepStatus.SKIPPED, condition_matched=False
                )

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
                if step.when is not None:
                    result.condition_matched = True
                return result
            except TimeoutError:
                last_error = f"Step '{step.name}' timed out after {step.timeout_seconds}s"
            except Exception as exc:  # noqa: BLE001  (el fallo del paso se reporta como estado, no se propaga)
                last_error = str(exc)

            if attempt < max_attempts - 1:
                sleep_time = delay * (2**attempt if backoff == "exponential" else 1)
                await asyncio.sleep(sleep_time)

        return StepResult(
            name=step.name,
            status=StepStatus.ERROR,
            error=last_error,
            condition_matched=True if step.when is not None else None,
        )

    async def _dispatch(self, step: StepSpec, context: dict[str, Any]) -> StepResult:
        start = time.time()
        if step.step_type == StepType.AGENT:
            return await self._run_agent(step, context, start)
        if step.step_type == StepType.TOOL:
            return await self._run_tool(step, context, start)
        if step.step_type == StepType.SWITCH:
            return await self._run_switch(step, context, start)
        if step.step_type == StepType.WAIT:
            return self._run_wait(step)
        if step.step_type == StepType.APPROVAL:
            return self._run_approval(step)
        if step.step_type == StepType.PARALLEL:
            return await self._run_parallel(step, context, start)
        raise ValueError(f"Unknown step type for step '{step.name}'")

    async def _run_agent(self, step: StepSpec, ctx: dict, start: float) -> StepResult:
        rendered_input = self._render(step.input_template or "", ctx)
        session_id = self._session_id or str(uuid.uuid4())
        result = await self._runtime.run(
            step.agent,
            rendered_input,
            session_id=session_id,
            parent_trace_id=self._parent_trace_id,
        )
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
            if self._eval_condition(condition, ctx, step.strict_conditions):
                goto = branch["goto"]
                break
        elapsed = (time.time() - start) * 1000
        return StepResult(
            name=step.name, status=StepStatus.SUCCESS, output={"goto": goto}, duration_ms=elapsed
        )

    async def _run_parallel(self, step: StepSpec, ctx: dict, start: float) -> StepResult:
        """Corre los sub-pasos a la vez y mergea sus salidas.

        Cada sub-paso es un StepSpec completo, así que `when`, `retry`,
        `timeout_seconds` y `on_error` funcionan por rama sin código nuevo. Las
        guardas se evalúan todas contra el mismo contexto: ninguna rama puede ver
        el resultado de una hermana, que es la consecuencia de correr en paralelo.
        """
        subs = step.parallel or []
        resultados = await asyncio.gather(
            *(self.execute_step(sub, ctx) for sub in subs), return_exceptions=True
        )

        salidas: dict[str, Any] = {}
        guardas: dict[str, bool] = {}
        errores: dict[str, str] = {}
        sub_results: dict[str, StepResult] = {}

        for sub, crudo in zip(subs, resultados, strict=True):
            # gather(return_exceptions=True): una rama que revienta fuera del
            # manejo de execute_step llega acá como excepción, no como StepResult.
            res = (
                StepResult(name=sub.name, status=StepStatus.ERROR, error=str(crudo))
                if isinstance(crudo, BaseException)
                else crudo
            )
            sub_results[sub.name] = res
            if res.condition_matched is not None:
                guardas[sub.name] = res.condition_matched
            if res.status == StepStatus.ERROR:
                errores[sub.name] = res.error or "error sin detalle"
            else:
                salidas[sub.name] = res.output

        # Una rama rota sólo tumba el paso si NO pidió `on_error: continue`; así el
        # paso paralelo hereda la misma política de fallo que los secuenciales.
        por_nombre = {sub.name: sub for sub in subs}
        fatales = [n for n in errores if por_nombre[n].on_error != "continue"]
        elapsed = (time.time() - start) * 1000
        return StepResult(
            name=step.name,
            status=StepStatus.ERROR if fatales else StepStatus.SUCCESS,
            output={
                "results": salidas,
                "_when": guardas,
                "_errors": errores,
                "_sub_results": sub_results,
            },
            error="; ".join(f"{n}: {errores[n]}" for n in fatales) or None,
            duration_ms=elapsed,
        )

    def _run_wait(self, step: StepSpec) -> StepResult:
        wait = step.wait or {}
        return StepResult(
            name=step.name,
            status=StepStatus.SUSPENDED,
            output={
                "resume_key": wait.get("resume_key"),
                "timeout_seconds": wait.get("timeout_seconds"),
            },
        )

    def _run_approval(self, step: StepSpec) -> StepResult:
        ap = step.approval or {}
        return StepResult(
            name=step.name,
            status=StepStatus.SUSPENDED,
            output={
                "resume_key": ap.get("resume_key"),
                "timeout_seconds": ap.get("timeout_seconds"),
                "approver": ap.get("approver"),
                "prompt": ap.get("prompt"),
                "on_reject": ap.get("on_reject"),
                "pending_approval": {
                    "step_name": step.name,
                    "approver": ap.get("approver"),
                    "prompt": ap.get("prompt"),
                },
            },
        )

    def _eval_condition(self, expr: str, context: dict, strict: bool) -> bool:
        env = self._jinja_strict if strict else self._jinja
        rendered = env.from_string(expr).render(**context).strip()
        return rendered.lower() in ("true", "1", "yes")

    def _render(self, template_str: str, context: dict) -> str:
        return self._jinja.from_string(template_str).render(**context)
