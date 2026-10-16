"""CLI against core 0.70: blocked/propuestas in `run`, a template core loads, `eval`."""

import logging

import yaml
from typer.testing import CliRunner

from astromesh_cli.commands import run as run_mod
from astromesh_cli.commands.new import render_agent_template
from astromesh_cli.main import app

runner = CliRunner()


def test_run_shows_blocked_and_propuestas(monkeypatch):
    body = {
        "answer": "I can't help with that request.",
        "blocked": True,
        "guardrail": {"direction": "input", "rule": "pii_detection", "reason": "pii detected"},
        "propuestas": [
            {"tool": "erp_crear", "tipo": "api", "destino": "erp", "operacion": "crear"}
        ],
        "usage": {"tokens_in": 0, "tokens_out": 0, "by_model": []},
    }
    monkeypatch.setattr(run_mod, "api_post_with_timeout", lambda *a, **k: body)
    result = runner.invoke(app, ["run", "support", "hi"])
    assert result.exit_code == 0
    assert "BLOCKED by guardrail" in result.stdout and "pii_detection" in result.stdout
    assert "erp_crear" in result.stdout


async def test_agent_template_loads_in_core_without_warnings(tmp_path, caplog):
    from astromesh.runtime.engine import AgentRuntime

    (tmp_path / "agents").mkdir()
    text = render_agent_template("bot", context_window=128000)
    spec = yaml.safe_load(text)["spec"]
    assert spec["model"]["primary"]["context_window"] == 128000
    (tmp_path / "agents" / "bot.agent.yaml").write_text(text)
    runtime = AgentRuntime(config_dir=str(tmp_path))
    with caplog.at_level(logging.WARNING, logger="astromesh.core.guardrails"):
        await runtime.bootstrap()
    assert "bot" in runtime._agents, runtime._agent_errors
    assert not caplog.records
    guard = runtime._agents["bot"]._guardrails
    assert guard.has_input and guard.has_output and guard.cost_limit["max_tokens"] == 4000


def test_template_without_context_window_leaves_it_commented():
    assert (
        "context_window"
        not in yaml.safe_load(render_agent_template("bot"))["spec"]["model"]["primary"]
    )


def test_eval_forwards_to_core_runner(monkeypatch):
    import astromesh.evals.__main__ as core_eval

    seen = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 1

    monkeypatch.setattr(core_eval, "main", fake_main)
    result = runner.invoke(app, ["eval", "cfg", "a.eval.yaml", "--out", "r.json"])
    assert result.exit_code == 1
    assert seen["argv"] == ["cfg", "a.eval.yaml", "--out", "r.json"]


def test_eval_without_evals_is_a_load_error(tmp_path):
    result = runner.invoke(app, ["eval", str(tmp_path)])
    assert result.exit_code == 2
