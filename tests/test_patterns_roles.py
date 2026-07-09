"""Assert each pattern requests the correct role at each decision point."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

from astromesh.orchestration.patterns import (
    ParallelFanOutPattern,
    PipelinePattern,
    PlanAndExecutePattern,
    ReActPattern,
)


@dataclass
class Resp:
    content: str
    tool_calls: list | None = None
    reasoning_content: str | None = None


def _roles_used(model_fn_mock):
    return [c.kwargs.get("role") for c in model_fn_mock.await_args_list]


async def test_react_uses_reasoner():
    model_fn = AsyncMock(return_value=Resp("done"))
    await ReActPattern().execute("q", {}, model_fn, AsyncMock(), [])
    assert _roles_used(model_fn) == ["reasoner"]


async def test_plan_and_execute_role_sequence():
    model_fn = AsyncMock(
        side_effect=[
            Resp('{"steps": [{"step": 1, "description": "do", "tool": null}]}'),
            Resp("step done"),
            Resp("final"),
        ]
    )
    await PlanAndExecutePattern().execute("q", {}, model_fn, AsyncMock(), [])
    assert _roles_used(model_fn) == ["planner", "worker", "synthesizer"]


async def test_parallel_fan_out_role_sequence():
    model_fn = AsyncMock(side_effect=[Resp('["a", "b"]'), Resp("ra"), Resp("rb"), Resp("agg")])
    await ParallelFanOutPattern().execute("q", {}, model_fn, AsyncMock(), [])
    roles = _roles_used(model_fn)
    assert roles[0] == "planner"
    assert roles[1] == "worker" and roles[2] == "worker"
    assert roles[-1] == "synthesizer"


async def test_pipeline_uses_stage_roles():
    model_fn = AsyncMock(side_effect=[Resp("a"), Resp("b"), Resp("c")])
    await PipelinePattern(stages=["analyze", "process", "synthesize"]).execute(
        "q", {}, model_fn, AsyncMock(), []
    )
    assert _roles_used(model_fn) == ["stage:analyze", "stage:process", "stage:synthesize"]
