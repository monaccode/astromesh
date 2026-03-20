"""Tests for output formatting utilities."""

from io import StringIO

from astromesh_cli.output import (
    console,
    error_console,
    print_cost_table,
    print_error,
    print_json,
    print_metrics_table,
    print_status_table,
    print_tool_list,
    print_trace_list,
    print_trace_tree,
)


def test_console_exists():
    assert console is not None


def test_error_console_exists():
    assert error_console is not None


def test_print_error_does_not_raise(capsys):
    # Just verify it doesn't crash
    print_error("test error")


def test_print_json_does_not_raise():
    print_json({"key": "value", "number": 42})


def test_print_status_table_does_not_raise():
    data = {
        "version": "0.1.0",
        "pid": 1234,
        "mode": "dev",
        "uptime_seconds": 123.4,
        "agents_loaded": 3,
    }
    print_status_table(data)


def test_print_trace_list_does_not_raise():
    traces = [
        {
            "trace_id": "abcdef1234567890",
            "agent": "test-agent",
            "started_at": "2026-01-01T00:00:00Z",
            "duration_ms": 250,
            "status": "ok",
        }
    ]
    print_trace_list(traces)


def test_print_trace_list_empty():
    print_trace_list([])


def test_print_trace_tree_does_not_raise():
    trace = {
        "trace_id": "abcdef1234567890",
        "agent": "test-agent",
        "spans": [
            {
                "name": "root-span",
                "duration_ms": 200,
                "children": [
                    {"name": "child-span", "duration_ms": 50, "children": []},
                ],
            }
        ],
    }
    print_trace_tree(trace)


def test_print_metrics_table_with_data():
    data = {
        "counters": {"requests_total": 100, "errors_total": 5},
        "histograms": {
            "request_duration_ms": {"count": 100, "avg": 123.4, "min": 10, "max": 500}
        },
    }
    print_metrics_table(data)


def test_print_metrics_table_empty():
    print_metrics_table({"counters": {}, "histograms": {}})


def test_print_cost_table_does_not_raise():
    data = {
        "counters": {"total_cost_usd": 0.0025},
        "histograms": {
            "cost_per_request": {"count": 10, "sum": 0.0025, "avg": 0.00025}
        },
    }
    print_cost_table(data)


def test_print_tool_list_does_not_raise():
    tools = [
        {
            "name": "search",
            "description": "Search the web",
            "parameters": {"query": "string", "limit": "int"},
        },
        {"name": "no-params-tool", "description": "Tool with no params"},
    ]
    print_tool_list(tools)


def test_print_tool_list_empty():
    print_tool_list([])
