"""Tests for the `ask` command against the core v0.36.0 response shape."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from astromesh_cli.main import app

runner = CliRunner()


def _mock_httpx_post(payload: dict):
    mock_response = MagicMock()
    mock_response.json.return_value = payload
    mock_response.raise_for_status = MagicMock()
    return mock_response


def test_ask_renders_answer_for_v036_shape():
    """The ask command must render `answer` (not the stale `response` field)."""
    payload = {
        "answer": "Esta es la respuesta del copiloto.",
        "steps": [],
        "usage": {"tokens_in": 12, "tokens_out": 8, "model": "llama3", "by_model": []},
        "trace": {"trace_id": "trace-xyz"},
    }
    with patch("astromesh_cli.client.httpx") as mock_httpx:
        mock_httpx.post.return_value = _mock_httpx_post(payload)
        result = runner.invoke(app, ["ask", "hola"])

    assert result.exit_code == 0
    assert "Esta es la respuesta del copiloto." in result.stdout
    # trace_id must come from the nested `trace` dict, not a stale top-level field.
    assert "trace-xyz" in result.stdout


def test_ask_falls_back_to_legacy_response_field():
    payload = {"response": "respuesta legacy", "tokens_used": 5}
    with patch("astromesh_cli.client.httpx") as mock_httpx:
        mock_httpx.post.return_value = _mock_httpx_post(payload)
        result = runner.invoke(app, ["ask", "hola"])

    assert result.exit_code == 0
    assert "respuesta legacy" in result.stdout


def test_ask_renders_by_model_table():
    payload = {
        "answer": "hola",
        "usage": {
            "tokens_in": 10,
            "tokens_out": 5,
            "model": "llama3",
            "by_model": [
                {
                    "provider": "ollama",
                    "model": "llama3",
                    "role": "default",
                    "calls": 2,
                    "tokens_in": 10,
                    "tokens_out": 5,
                    "cost": 0.0,
                },
            ],
        },
        "trace": {"trace_id": "trace-abc"},
    }
    with patch("astromesh_cli.client.httpx") as mock_httpx:
        mock_httpx.post.return_value = _mock_httpx_post(payload)
        result = runner.invoke(app, ["ask", "hola"])

    assert result.exit_code == 0
    assert "Por modelo" in result.stdout
    assert "ollama" in result.stdout


def test_ask_json_output_unchanged():
    payload = {"answer": "hola", "usage": {"tokens_in": 1, "tokens_out": 1}}
    with patch("astromesh_cli.client.httpx") as mock_httpx:
        mock_httpx.post.return_value = _mock_httpx_post(payload)
        result = runner.invoke(app, ["ask", "hola", "--json"])

    assert result.exit_code == 0
    assert '"answer"' in result.stdout
