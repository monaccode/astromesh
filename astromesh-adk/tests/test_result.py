from astromesh_adk.result import RunResult, StreamEvent


def test_run_result_from_runtime_dict():
    """RunResult is built from the dict returned by AgentRuntime.run()."""
    runtime_result = {
        "answer": "CRISPR is a gene editing tool.",
        "steps": [
            {"thought": "Need to search", "action": "web_search", "action_input": {"query": "CRISPR"}, "observation": "Found info", "result": None}
        ],
        "trace": _make_trace_dict(),
    }
    result = RunResult.from_runtime(runtime_result)

    assert result.answer == "CRISPR is a gene editing tool."
    assert len(result.steps) == 1
    assert result.steps[0]["action"] == "web_search"
    assert result.cost >= 0
    assert result.tokens["input"] >= 0
    assert result.tokens["output"] >= 0
    assert result.latency_ms >= 0
    assert isinstance(result.model, str)


def test_run_result_from_runtime_no_trace():
    """RunResult works when trace is None."""
    runtime_result = {"answer": "Hello", "steps": [], "trace": None}
    result = RunResult.from_runtime(runtime_result)

    assert result.answer == "Hello"
    assert result.cost == 0.0
    assert result.tokens == {"input": 0, "output": 0}
    assert result.latency_ms == 0.0
    assert result.model == ""


def test_stream_event_step():
    event = StreamEvent(type="step", step={"action": "search"})
    assert event.type == "step"
    assert event.step == {"action": "search"}
    assert event.content is None
    assert event.result is None


def test_stream_event_token():
    event = StreamEvent(type="token", content="Hello")
    assert event.content == "Hello"


def test_stream_event_done():
    result = RunResult(answer="done", steps=[], trace=None, cost=0.0, tokens={"input": 0, "output": 0}, latency_ms=0.0, model="")
    event = StreamEvent(type="done", result=result)
    assert event.result.answer == "done"


def _make_trace_dict():
    """Helper: build a minimal trace dict with one llm.complete span."""
    return {
        "agent_name": "test",
        "session_id": "s1",
        "trace_id": "t1",
        "spans": [
            {
                "name": "agent.run",
                "span_id": "root",
                "parent_span_id": None,
                "duration_ms": 1500.0,
                "attributes": {},
            },
            {
                "name": "llm.complete",
                "span_id": "llm1",
                "parent_span_id": "root",
                "duration_ms": 1200.0,
                "attributes": {
                    "model": "gpt-4o",
                    "input_tokens": 500,
                    "output_tokens": 200,
                    "cost": 0.003,
                },
            },
        ],
    }
