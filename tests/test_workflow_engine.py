# tests/test_workflow_engine.py
import pytest
from unittest.mock import AsyncMock

from astromesh.workflow import WorkflowEngine
from astromesh.workflow.models import WorkflowRunResult


@pytest.fixture
def workflows_dir(tmp_path):
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    return wf_dir


def _write_workflow(wf_dir, name, content):
    (wf_dir / f"{name}.workflow.yaml").write_text(content)


@pytest.fixture
def mock_runtime():
    runtime = AsyncMock()
    runtime.run = AsyncMock(return_value={"answer": "agent result", "steps": []})
    return runtime


@pytest.fixture
def mock_tool_registry():
    registry = AsyncMock()
    registry.execute = AsyncMock(return_value={"result": "stored"})
    return registry


class TestWorkflowEngine:
    async def test_bootstrap_loads_workflows(self, workflows_dir, mock_runtime, mock_tool_registry):
        _write_workflow(workflows_dir, "test", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: test-wf
spec:
  steps:
    - name: s1
      agent: a1
      input: "hello"
""")
        engine = WorkflowEngine(
            workflows_dir=str(workflows_dir),
            runtime=mock_runtime,
            tool_registry=mock_tool_registry,
        )
        await engine.bootstrap()
        assert "test-wf" in engine.list_workflows()

    async def test_list_workflows(self, workflows_dir, mock_runtime, mock_tool_registry):
        _write_workflow(workflows_dir, "wf1", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: wf-alpha
spec:
  steps:
    - name: s1
      agent: a1
      input: "hi"
""")
        _write_workflow(workflows_dir, "wf2", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: wf-beta
spec:
  steps:
    - name: s1
      agent: a2
      input: "hi"
""")
        engine = WorkflowEngine(
            workflows_dir=str(workflows_dir),
            runtime=mock_runtime,
            tool_registry=mock_tool_registry,
        )
        await engine.bootstrap()
        names = engine.list_workflows()
        assert set(names) == {"wf-alpha", "wf-beta"}

    async def test_run_sequential_steps(self, workflows_dir, mock_runtime, mock_tool_registry):
        _write_workflow(workflows_dir, "seq", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: seq-wf
spec:
  steps:
    - name: step1
      agent: agent1
      input: "{{ trigger.query }}"
    - name: step2
      agent: agent2
      input: "{{ steps.step1.output }}"
""")
        engine = WorkflowEngine(
            workflows_dir=str(workflows_dir),
            runtime=mock_runtime,
            tool_registry=mock_tool_registry,
        )
        await engine.bootstrap()
        result = await engine.run("seq-wf", trigger={"query": "hello"})
        assert isinstance(result, WorkflowRunResult)
        assert result.status == "completed"
        assert "step1" in result.steps
        assert "step2" in result.steps
        assert mock_runtime.run.call_count == 2

    async def test_run_with_switch_goto(self, workflows_dir, mock_runtime, mock_tool_registry):
        mock_runtime.run = AsyncMock(
            return_value={"answer": "ok", "data": {"score": 9}, "steps": []}
        )
        _write_workflow(workflows_dir, "switch", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: switch-wf
spec:
  steps:
    - name: score
      agent: scorer
      input: "{{ trigger.query }}"
    - name: decide
      switch:
        - when: "{{ steps.score.output.data.score > 7 }}"
          goto: high
        - default: true
          goto: low
    - name: high
      agent: high-handler
      input: "high path"
    - name: low
      agent: low-handler
      input: "low path"
""")
        engine = WorkflowEngine(
            workflows_dir=str(workflows_dir),
            runtime=mock_runtime,
            tool_registry=mock_tool_registry,
        )
        await engine.bootstrap()
        result = await engine.run("switch-wf", trigger={"query": "test"})
        assert result.status == "completed"
        # Should have executed: score -> decide -> high (skipping low)
        assert "score" in result.steps
        assert "decide" in result.steps
        assert "high" in result.steps
        assert "low" not in result.steps

    async def test_run_nonexistent_workflow(self, workflows_dir, mock_runtime, mock_tool_registry):
        engine = WorkflowEngine(
            workflows_dir=str(workflows_dir),
            runtime=mock_runtime,
            tool_registry=mock_tool_registry,
        )
        await engine.bootstrap()
        with pytest.raises(ValueError, match="not found"):
            await engine.run("ghost-wf", trigger={})

    async def test_run_on_error_goto(self, workflows_dir, mock_runtime, mock_tool_registry):
        call_count = 0

        async def conditional_run(agent_name, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if agent_name == "bad-agent":
                raise Exception("agent failed")
            return {"answer": "fallback ok", "steps": []}

        mock_runtime.run = conditional_run
        _write_workflow(workflows_dir, "error", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: error-wf
spec:
  steps:
    - name: risky
      agent: bad-agent
      input: "go"
      on_error: fallback
    - name: fallback
      agent: safe-agent
      input: "recover"
""")
        engine = WorkflowEngine(
            workflows_dir=str(workflows_dir),
            runtime=mock_runtime,
            tool_registry=mock_tool_registry,
        )
        await engine.bootstrap()
        result = await engine.run("error-wf", trigger={})
        assert result.status == "completed"
        assert "fallback" in result.steps
        assert result.steps["fallback"].status.value == "success"

    async def test_run_produces_trace(self, workflows_dir, mock_runtime, mock_tool_registry):
        _write_workflow(workflows_dir, "traced", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: traced-wf
spec:
  steps:
    - name: s1
      agent: a1
      input: "hello"
""")
        engine = WorkflowEngine(
            workflows_dir=str(workflows_dir),
            runtime=mock_runtime,
            tool_registry=mock_tool_registry,
        )
        await engine.bootstrap()
        result = await engine.run("traced-wf", trigger={"query": "hi"})
        assert result.trace is not None
        assert "trace_id" in result.trace
        assert len(result.trace["spans"]) >= 2  # workflow.run + step span
