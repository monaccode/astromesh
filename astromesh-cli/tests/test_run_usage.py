from astromesh_cli.commands.run import _format_run_output


def test_reads_answer_and_usage_totals():
    data = {
        "answer": "hola",
        "steps": [],
        "usage": {"tokens_in": 10, "tokens_out": 5, "model": "llama3", "by_model": []},
    }
    text, subtitle, rows = _format_run_output(data)
    assert text == "hola"
    assert "15" in subtitle or ("10" in subtitle and "5" in subtitle)
    assert rows == []


def test_builds_by_model_rows():
    data = {
        "answer": "hola",
        "usage": {
            "tokens_in": 10,
            "tokens_out": 5,
            "model": "llama3",
            "by_model": [
                {"provider": "ollama", "model": "llama3", "role": "default",
                 "calls": 2, "tokens_in": 10, "tokens_out": 5, "cost": 0.0},
            ],
        },
    }
    _text, _subtitle, rows = _format_run_output(data)
    assert rows[0]["provider"] == "ollama"
    assert rows[0]["model"] == "llama3"


def test_falls_back_to_legacy_fields():
    # Pre-v0.36 / daemon that returns response+tokens_used and no usage object.
    data = {"response": "hola", "tokens_used": 42}
    text, subtitle, rows = _format_run_output(data)
    assert text == "hola"
    assert "42" in subtitle
    assert rows == []
