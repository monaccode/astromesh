from astromesh.runtime.engine import _truncate, _normalize_tool_calls


def test_truncate_none():
    assert _truncate(None, 100) == ""


def test_truncate_empty():
    assert _truncate("", 100) == ""


def test_truncate_within_limit():
    assert _truncate("hello", 100) == "hello"


def test_truncate_at_limit():
    text = "a" * 100
    assert _truncate(text, 100) == text


def test_truncate_over_limit():
    text = "a" * 200
    result = _truncate(text, 100)
    assert len(result) > 100
    assert result.startswith("a" * 100)
    assert "[truncated at 200 chars]" in result


def test_normalize_flat_dict():
    raw = [{"id": "1", "name": "search", "arguments": {"q": "test"}}]
    assert _normalize_tool_calls(raw) == raw


def test_normalize_openai_nested():
    raw = [{"id": "call_1", "function": {"name": "search", "arguments": {"q": "test"}}}]
    result = _normalize_tool_calls(raw)
    assert result == [{"id": "call_1", "name": "search", "arguments": {"q": "test"}}]


def test_normalize_empty():
    assert _normalize_tool_calls([]) == []


def test_normalize_non_dict():
    result = _normalize_tool_calls(["not_a_dict"])
    assert result == [{"raw": "not_a_dict"}]


def test_normalize_json_string_args():
    raw = [{"id": "call_1", "function": {"name": "search", "arguments": '{"q": "test"}'}}]
    result = _normalize_tool_calls(raw)
    assert result == [{"id": "call_1", "name": "search", "arguments": {"q": "test"}}]
