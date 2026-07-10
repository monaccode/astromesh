# astromesh/workflow/__init__.py
from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from astromesh.observability.tracing import TracingContext, SpanStatus
from astromesh.workflow.executor import StepExecutor
from astromesh.workflow.loader import WorkflowLoader
from astromesh.workflow.models import (
    StepStatus as WfStepStatus,
    StepType,
    WorkflowRun,
    WorkflowRunResult,
    WorkflowSpec,
)
from astromesh.workflow.store import InMemoryRunStore, WorkflowRunStore


class WorkflowEngine:
    """Loads workflow YAML specs and orchestrates multi-step execution."""

    def __init__(
        self,
        workflows_dir: str,
        runtime,
        tool_registry,
        store: WorkflowRunStore | None = None,
    ):
        self._workflows_dir = workflows_dir
        self._runtime = runtime
        self._tool_registry = tool_registry
        self._workflows: dict[str, WorkflowSpec] = {}
        self._executor: StepExecutor | None = None
        self._store: WorkflowRunStore = store if store is not None else InMemoryRunStore()

    async def bootstrap(self):
        loader = WorkflowLoader(self._workflows_dir)
        self._workflows = loader.load_all()
        self._executor = StepExecutor(runtime=self._runtime, tool_registry=self._tool_registry)

        if hasattr(self._store, "initialize"):
            await self._store.initialize()
        await self.mark_orphaned_failed()
        await self.sweep_expired(now=datetime.now(UTC).isoformat())

    def list_workflows(self) -> list[str]:
        return list(self._workflows.keys())

    def get_workflow(self, name: str) -> WorkflowSpec | None:
        return self._workflows.get(name)

    async def run(self, workflow_name: str, trigger: dict[str, Any]) -> WorkflowRunResult:
        """Starts a new durable run: creates a WorkflowRun in the store, then drives it.

        Synchronous façade: a workflow with no WAIT step returns the full
        WorkflowRunResult (status "completed"/"failed") as before. A workflow that
        hits a WAIT step returns early with status "suspended" and a run_id that
        can be used to resume later.
        """
        wf = self._workflows.get(workflow_name)
        if not wf:
            raise ValueError(f"Workflow '{workflow_name}' not found")

        run = WorkflowRun(
            run_id=str(uuid.uuid4()),
            workflow_name=workflow_name,
            status="running",
            current_index=0,
            context={"trigger": trigger, "steps": {}},
            created_at=datetime.now(UTC).isoformat(),
        )
        await self._store.create(run)
        return await self._drive(wf, run)

    async def resume(self, run_id: str, payload: dict[str, Any]) -> WorkflowRunResult:
        """Resumes a suspended run: injects `payload` as the wait step's output,
        marks the run "running" again, and drives it to completion (or the next
        suspend). Raises ValueError if the run doesn't exist or isn't suspended.
        """
        run = await self._store.load(run_id)
        if run is None:
            raise ValueError(f"Run '{run_id}' not found")
        if run.status != "suspended":
            raise ValueError(f"Run '{run_id}' is not suspended (status={run.status})")

        wf = self._workflows.get(run.workflow_name)
        if not wf:
            raise ValueError(f"Workflow '{run.workflow_name}' not found")

        # el step wait está en current_index-1; inyectar el payload como su output
        wait_idx = run.current_index - 1
        if 0 <= wait_idx < len(wf.steps):
            run.context["steps"][wf.steps[wait_idx].name] = {"output": payload}
        run.context["resume"] = payload
        run.status = "running"
        await self._store.save(run)
        return await self._drive(wf, run)

    async def _drive(self, wf: WorkflowSpec, run: WorkflowRun) -> WorkflowRunResult:
        """Executes wf from run.current_index; checkpoints the run after each step;
        stops and persists as "suspended" if a step returns SUSPENDED (a WAIT step).
        """
        tracing = TracingContext(agent_name=f"workflow:{run.workflow_name}", session_id="")
        root_span = tracing.start_span(
            "workflow.run", {"workflow": run.workflow_name, "trigger_type": wf.trigger}
        )

        start = time.time()
        step_results: dict[str, Any] = {}
        context = run.context
        status = "completed"

        try:
            # Build step index for goto lookups
            step_index = {s.name: i for i, s in enumerate(wf.steps)}
            i = run.current_index

            while i < len(wf.steps):
                step = wf.steps[i]
                step_span = tracing.start_span(
                    f"step.{step.name}",
                    {"step_type": step.step_type.value},
                    parent_span_id=root_span.span_id,
                )

                result = await self._executor.execute_step(step, context)
                step_results[step.name] = result

                if result.status == WfStepStatus.SUSPENDED:
                    tracing.finish_span(step_span)
                    run.status = "suspended"
                    run.current_index = i + 1  # resume after the wait
                    run.resume_key = (result.output or {}).get("resume_key")
                    timeout = (result.output or {}).get("timeout_seconds")
                    if timeout:
                        run.expires_at = (
                            datetime.now(UTC) + timedelta(seconds=timeout)
                        ).isoformat()
                    run.updated_at = datetime.now(UTC).isoformat()
                    await self._store.save(run)
                    tracing.finish_span(root_span)
                    elapsed = (time.time() - start) * 1000
                    return WorkflowRunResult(
                        workflow_name=run.workflow_name,
                        status="suspended",
                        steps=step_results,
                        trace=tracing.to_dict(),
                        duration_ms=elapsed,
                        run_id=run.run_id,
                    )

                if result.status == WfStepStatus.ERROR:
                    tracing.finish_span(step_span, status=SpanStatus.ERROR)
                    if step.on_error and step.on_error != "fail":
                        # Jump to error handler step
                        context["steps"][step.name] = {
                            "output": result.output,
                            "error": result.error,
                        }
                        if step.on_error in step_index:
                            i = step_index[step.on_error]
                            run.current_index = i
                            run.updated_at = datetime.now(UTC).isoformat()
                            await self._store.save(run)
                            continue
                    status = "failed"
                    run.error = result.error
                    break
                else:
                    tracing.finish_span(step_span)

                # Store result in context for subsequent steps
                context["steps"][step.name] = {"output": result.output}

                # Handle switch goto — jump to target step, execute it, then stop
                if step.step_type == StepType.SWITCH and result.output:
                    goto = result.output.get("goto")
                    if goto and goto in step_index:
                        goto_step = wf.steps[step_index[goto]]
                        goto_span = tracing.start_span(
                            f"step.{goto_step.name}",
                            {"step_type": goto_step.step_type.value},
                            parent_span_id=root_span.span_id,
                        )
                        goto_result = await self._executor.execute_step(goto_step, context)
                        step_results[goto_step.name] = goto_result
                        if goto_result.status == WfStepStatus.SUSPENDED:
                            tracing.finish_span(goto_span)
                            run.status = "suspended"
                            run.current_index = step_index[goto_step.name] + 1  # resume after the wait
                            run.resume_key = (goto_result.output or {}).get("resume_key")
                            timeout = (goto_result.output or {}).get("timeout_seconds")
                            if timeout:
                                run.expires_at = (
                                    datetime.now(UTC) + timedelta(seconds=timeout)
                                ).isoformat()
                            run.updated_at = datetime.now(UTC).isoformat()
                            await self._store.save(run)
                            tracing.finish_span(root_span)
                            elapsed = (time.time() - start) * 1000
                            return WorkflowRunResult(
                                workflow_name=run.workflow_name,
                                status="suspended",
                                steps=step_results,
                                trace=tracing.to_dict(),
                                duration_ms=elapsed,
                                run_id=run.run_id,
                            )
                        if goto_result.status == WfStepStatus.ERROR:
                            tracing.finish_span(goto_span, status=SpanStatus.ERROR)
                            status = "failed"
                            run.error = goto_result.error
                        else:
                            tracing.finish_span(goto_span)
                            context["steps"][goto_step.name] = {"output": goto_result.output}
                        run.current_index = step_index[goto_step.name] + 1
                        break

                run.current_index = i + 1
                run.updated_at = datetime.now(UTC).isoformat()
                await self._store.save(run)
                i += 1

        except Exception:
            status = "failed"
            run.status = status
            run.updated_at = datetime.now(UTC).isoformat()
            await self._store.save(run)
            tracing.finish_span(root_span, status=SpanStatus.ERROR)
            elapsed = (time.time() - start) * 1000
            return WorkflowRunResult(
                workflow_name=run.workflow_name,
                status=status,
                steps=step_results,
                trace=tracing.to_dict(),
                duration_ms=elapsed,
                run_id=run.run_id,
            )

        run.status = status
        run.updated_at = datetime.now(UTC).isoformat()
        await self._store.save(run)

        tracing.finish_span(root_span)
        elapsed = (time.time() - start) * 1000

        # Output is the last executed step's output
        last_step_name = list(step_results.keys())[-1] if step_results else None
        output = step_results[last_step_name].output if last_step_name else None

        return WorkflowRunResult(
            workflow_name=run.workflow_name,
            status=status,
            steps=step_results,
            output=output,
            trace=tracing.to_dict(),
            duration_ms=elapsed,
            run_id=run.run_id,
        )

    async def sweep_expired(self, now: str) -> int:
        n = 0
        for run in await self._store.list_by_status("suspended"):
            if run.expires_at and run.expires_at < now:
                run.status = "expired"
                run.error = "wait timed out"
                await self._store.save(run)
                n += 1
        return n

    async def mark_orphaned_failed(self) -> int:
        n = 0
        for run in await self._store.list_by_status("running"):
            run.status = "failed"
            run.error = "orphaned: process died mid-run"
            await self._store.save(run)
            n += 1
        return n
