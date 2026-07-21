"""Token usage derived from a trace, shared by the REST and WebSocket surfaces."""

from astromesh.api.usage import usage_from_trace


def test_sums_input_and_output_tokens_across_spans():
    trace = {
        "spans": [
            {"attributes": {"input_tokens": 10, "output_tokens": 5}},
            {"attributes": {"input_tokens": 3, "output_tokens": 7}},
        ]
    }
    assert usage_from_trace(trace) == {"tokens_in": 13, "tokens_out": 12, "model": ""}


def test_reads_legacy_nested_metadata_usage():
    trace = {
        "spans": [
            {
                "attributes": {
                    "metadata": {
                        "usage": {"prompt_tokens": 4, "completion_tokens": 6},
                        "model": "gpt-4o-mini",
                    }
                }
            }
        ]
    }
    assert usage_from_trace(trace) == {"tokens_in": 4, "tokens_out": 6, "model": "gpt-4o-mini"}


def test_takes_the_first_model_it_sees():
    trace = {
        "spans": [
            {"attributes": {"input_tokens": 1, "metadata": {"model": "first"}}},
            {"attributes": {"input_tokens": 1, "metadata": {"model": "second"}}},
        ]
    }
    assert usage_from_trace(trace)["model"] == "first"


def test_adds_direct_and_legacy_tokens_from_the_same_span():
    trace = {
        "spans": [
            {
                "attributes": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "metadata": {"usage": {"prompt_tokens": 1, "completion_tokens": 2}},
                }
            }
        ]
    }
    assert usage_from_trace(trace) == {"tokens_in": 11, "tokens_out": 7, "model": ""}


def test_returns_none_when_no_tokens_were_reported():
    assert usage_from_trace({"spans": [{"attributes": {"tool": "search"}}]}) is None


def test_returns_none_for_empty_or_missing_traces():
    assert usage_from_trace(None) is None
    assert usage_from_trace({}) is None
    assert usage_from_trace({"spans": []}) is None


def test_tolerates_malformed_traces_without_raising():
    # A trace comes from the runtime, but nothing enforces its shape here.
    assert usage_from_trace({"spans": "not-a-list"}) is None
    assert usage_from_trace({"spans": ["not-a-dict"]}) is None
    assert usage_from_trace({"spans": [{"attributes": None}]}) is None
    assert usage_from_trace("not-a-dict") is None


def test_reads_model_from_direct_span_attribute():
    """El runtime escribe el modelo como atributo directo, no bajo metadata."""
    trace = {
        "spans": [
            {
                "attributes": {
                    "model": "gpt-4o-mini",
                    "provider": "openai",
                    "input_tokens": 10,
                    "output_tokens": 4,
                }
            }
        ]
    }
    assert usage_from_trace(trace) == {
        "tokens_in": 10,
        "tokens_out": 4,
        "model": "gpt-4o-mini",
    }


def test_direct_model_attribute_wins_over_legacy_metadata():
    trace = {
        "spans": [
            {
                "attributes": {
                    "model": "directo",
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "metadata": {"model": "heredado"},
                }
            }
        ]
    }
    assert usage_from_trace(trace)["model"] == "directo"


def test_first_model_wins_across_spans():
    trace = {
        "spans": [
            {"attributes": {"model": "primero", "input_tokens": 1, "output_tokens": 1}},
            {"attributes": {"model": "segundo", "input_tokens": 1, "output_tokens": 1}},
        ]
    }
    assert usage_from_trace(trace)["model"] == "primero"
