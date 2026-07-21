"""Token usage derived from a trace, shared by the REST and WebSocket surfaces."""

from astromesh.api.usage import usage_from_trace


def test_sums_input_and_output_tokens_across_spans():
    trace = {
        "spans": [
            {"attributes": {"input_tokens": 10, "output_tokens": 5}},
            {"attributes": {"input_tokens": 3, "output_tokens": 7}},
        ]
    }
    assert usage_from_trace(trace) == {
        "tokens_in": 13,
        "tokens_out": 12,
        "model": "",
        "by_model": [],
    }


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
    assert usage_from_trace(trace) == {
        "tokens_in": 4,
        "tokens_out": 6,
        "model": "gpt-4o-mini",
        "by_model": [],
    }


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
    assert usage_from_trace(trace) == {
        "tokens_in": 11,
        "tokens_out": 7,
        "model": "",
        "by_model": [],
    }


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
        "by_model": [
            {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "role": "default",
                "calls": 1,
                "tokens_in": 10,
                "tokens_out": 4,
                "cost": 0.0,
            }
        ],
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


def test_by_model_groups_by_provider_model_and_role():
    trace = {
        "spans": [
            {
                "attributes": {
                    "model": "gpt-4o",
                    "provider": "openai",
                    "resolved_role": "reasoning",
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cost": 0.5,
                }
            },
            {
                "attributes": {
                    "model": "gpt-4o",
                    "provider": "openai",
                    "resolved_role": "reasoning",
                    "input_tokens": 50,
                    "output_tokens": 10,
                    "cost": 0.25,
                }
            },
            {
                "attributes": {
                    "model": "centinela-4b",
                    "provider": "ollama",
                    "resolved_role": "classification",
                    "input_tokens": 30,
                    "output_tokens": 5,
                    "cost": 0.0,
                }
            },
        ]
    }
    usage = usage_from_trace(trace)

    assert usage["tokens_in"] == 180
    assert usage["tokens_out"] == 35
    assert usage["by_model"] == [
        {
            "provider": "openai",
            "model": "gpt-4o",
            "role": "reasoning",
            "calls": 2,
            "tokens_in": 150,
            "tokens_out": 30,
            "cost": 0.75,
        },
        {
            "provider": "ollama",
            "model": "centinela-4b",
            "role": "classification",
            "calls": 1,
            "tokens_in": 30,
            "tokens_out": 5,
            "cost": 0.0,
        },
    ]


def test_same_model_under_different_roles_are_separate_rows():
    trace = {
        "spans": [
            {
                "attributes": {
                    "model": "gpt-4o-mini",
                    "provider": "openai",
                    "resolved_role": "reasoning",
                    "input_tokens": 10,
                    "output_tokens": 2,
                }
            },
            {
                "attributes": {
                    "model": "gpt-4o-mini",
                    "provider": "openai",
                    "resolved_role": "summarization",
                    "input_tokens": 8,
                    "output_tokens": 1,
                }
            },
        ]
    }
    rows = usage_from_trace(trace)["by_model"]
    assert len(rows) == 2
    assert {r["role"] for r in rows} == {"reasoning", "summarization"}


def test_role_defaults_when_absent():
    trace = {
        "spans": [
            {"attributes": {"model": "m", "provider": "p", "input_tokens": 1, "output_tokens": 1}}
        ]
    }
    assert usage_from_trace(trace)["by_model"][0]["role"] == "default"


def test_falls_back_to_role_when_resolved_role_missing():
    trace = {
        "spans": [
            {
                "attributes": {
                    "model": "m",
                    "provider": "p",
                    "role": "classification",
                    "input_tokens": 1,
                    "output_tokens": 1,
                }
            }
        ]
    }
    assert usage_from_trace(trace)["by_model"][0]["role"] == "classification"


def test_spans_without_model_contribute_tokens_but_no_row():
    trace = {
        "spans": [
            {"attributes": {"input_tokens": 7, "output_tokens": 3}},
            {"attributes": {"model": "m", "provider": "p", "input_tokens": 1, "output_tokens": 1}},
        ]
    }
    usage = usage_from_trace(trace)
    assert usage["tokens_in"] == 8
    assert len(usage["by_model"]) == 1


def test_non_numeric_cost_is_ignored_not_fatal():
    trace = {
        "spans": [
            {
                "attributes": {
                    "model": "m",
                    "provider": "p",
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cost": "no-es-un-numero",
                }
            }
        ]
    }
    assert usage_from_trace(trace)["by_model"][0]["cost"] == 0.0


def test_legacy_only_trace_reports_empty_by_model():
    trace = {
        "spans": [
            {"attributes": {"metadata": {"usage": {"prompt_tokens": 4, "completion_tokens": 6}}}}
        ]
    }
    usage = usage_from_trace(trace)
    assert usage["tokens_in"] == 4
    assert usage["by_model"] == []
