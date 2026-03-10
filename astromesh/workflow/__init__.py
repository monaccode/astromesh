# astromesh/workflow/__init__.py
from __future__ import annotations

import time
from typing import Any

from astromesh.observability.tracing import TracingContext, SpanStatus
from astromesh.workflow.executor import StepExecutor
from astromesh.workflow.loader import WorkflowLoader
from astromesh.workflow.models import (
    StepStatus as WfStepStatus,
    StepType,
    WorkflowRunResult,
    WorkflowSpec,
)


class WorkflowEngine:
    """Loads workflow YAML specs and orchestrates multi-step execution."""

    def __init__(self, workflows_dir: str, runtime, tool_registry):
        self._workflows_dir = workflows_dir
        self._runtime = runtime
        self._tool_registry = tool_registry
        self._workflows: dict[str, WorkflowSpec] = {}
        self._executor: StepExecutor | None = None

    async def bootstrap(self):
        loader = WorkflowLoader(self._workflows_dir)
        self._workflows = loader.load_all()
        self._executor = StepExecutor(
            runtime=self._runtime, tool_registry=self._tool_registry
        )

    def list_workflows(self) -> list[str]:
        return list(self._workflows.keys())

    def get_workflow(self, name: str) -> WorkflowSpec | None:
        return self._workflows.get(name)

    async def run(
        self, workflow_name: str, trigger: dict[str, Any]
    ) -> WorkflowRunResult:
        wf = self._workflows.get(workflow_name)
        if not wf:
            raise ValueError(f"Workflow '{workflow_name}' not found")

        tracing = TracingContext(agent_name=f"workflow:{workflow_name}", session_id="")
        root_span = tracing.start_span(
            "workflow.run", {"workflow": workflow_name, "trigger_type": wf.trigger}
        )

        start = time.time()
        step_results: dict[str, Any] = {}
        context: dict[str, Any] = {"trigger": trigger, "steps": {}}
        status = "completed"

        try:
            # Build step index for goto lookups
            step_index = {s.name: i for i, s in enumerate(wf.steps)}
            i = 0

            while i < len(wf.steps):
                step = wf.steps[i]
                step_span = tracing.start_span(
                    f"step.{step.name}",
                    {"step_type": step.step_type.value},
                    parent_span_id=root_span.span_id,
                )

                result = await self._executor.execute_step(step, context)
                step_results[step.name] = result

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
                            continue
                    status = "failed"
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
                        goto_result = await self._executor.execute_step(
                            goto_step, context
                        )
                        step_results[goto_step.name] = goto_result
                        if goto_result.status == WfStepStatus.ERROR:
                            tracing.finish_span(goto_span, status=SpanStatus.ERROR)
                            status = "failed"
                        else:
                            tracing.finish_span(goto_span)
                            context["steps"][goto_step.name] = {
                                "output": goto_result.output
                            }
                        break

                i += 1

        except Exception:
            status = "failed"
            tracing.finish_span(root_span, status=SpanStatus.ERROR)
            elapsed = (time.time() - start) * 1000
            return WorkflowRunResult(
                workflow_name=workflow_name,
                status=status,
                steps=step_results,
                trace=tracing.to_dict(),
                duration_ms=elapsed,
            )

        tracing.finish_span(root_span)
        elapsed = (time.time() - start) * 1000

        # Output is the last executed step's output
        last_step_name = list(step_results.keys())[-1] if step_results else None
        output = step_results[last_step_name].output if last_step_name else None

        return WorkflowRunResult(
            workflow_name=workflow_name,
            status=status,
            steps=step_results,
            output=output,
            trace=tracing.to_dict(),
            duration_ms=elapsed,
        )
