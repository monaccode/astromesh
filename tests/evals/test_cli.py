"""CLI: exit codes, --out, errores de carga."""

import json

import pytest
import yaml

from astromesh.core import tokens
from astromesh.evals import __main__ as cli
from astromesh.providers.base import CompletionResponse
from astromesh.runtime.engine import AgentRuntime


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


@pytest.fixture
def modelo_ok(monkeypatch):
    """Todo agente arrancado responde 'ok' sin red."""
    original = AgentRuntime.bootstrap

    async def bootstrap(self):
        await original(self)
        for agente in self._agents.values():

            async def route(messages, requirements=None, **kw):
                return CompletionResponse(
                    content="ok",
                    model="m",
                    provider="p",
                    usage={"input_tokens": 7, "output_tokens": 1},
                    latency_ms=1.0,
                    cost=0.0,
                )

            agente._routers["default"].route = route

    monkeypatch.setattr(AgentRuntime, "bootstrap", bootstrap)


def _config(tmp_path, expect="ok", agente="lucia"):
    d = tmp_path / "config"
    (d / "agents").mkdir(parents=True)
    (d / "evals").mkdir()
    (d / "agents" / "lucia.agent.yaml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "astromesh/v1",
                "kind": "Agent",
                "metadata": {"name": "lucia", "version": "0.1.0"},
                "spec": {
                    "identity": {"description": "demo"},
                    "model": {"primary": {"provider": "ollama", "model": "llama3"}},
                    "prompts": {"system": "sos un agente"},
                },
            }
        )
    )
    (d / "evals" / "e.eval.yaml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "astromesh/v1",
                "kind": "Eval",
                "metadata": {"name": "e"},
                "spec": {
                    "agent": agente,
                    "thresholds": {"pass_rate": 1.0},
                    "cases": [{"id": "c", "turns": ["hola"], "expect": [{"contains": expect}]}],
                },
            }
        )
    )
    return d


def test_todo_pasa_sale_0_y_escribe_out(tmp_path, modelo_ok, capsys):
    d = _config(tmp_path)
    out = tmp_path / "r.json"
    assert cli.main([str(d), "--out", str(out)]) == 0
    rep = json.loads(out.read_text())
    assert set(rep) == {"run_id", "evals"}
    (ev,) = rep["evals"]
    assert ev["name"] == "e"
    assert ev["passed"] is True
    assert ev["cases"][0]["status"] == "pass"
    assert {"tokens_in", "cost", "latency_ms", "motivos"} <= set(ev["cases"][0])
    assert "e" in capsys.readouterr().out


def test_bajo_umbral_sale_1(tmp_path, modelo_ok):
    assert cli.main([str(_config(tmp_path, expect="nunca"))]) == 1


def test_agente_inexistente_sale_2_sin_correr(tmp_path, modelo_ok, capsys):
    assert cli.main([str(_config(tmp_path, agente="nadie"))]) == 2
    assert "nadie" in capsys.readouterr().err


def test_eval_invalido_sale_2(tmp_path):
    d = _config(tmp_path)
    (d / "evals" / "roto.eval.yaml").write_text("kind: Eval\n")
    assert cli.main([str(d)]) == 2


def test_sin_evals_sale_2(tmp_path):
    d = tmp_path / "vacio"
    d.mkdir()
    assert cli.main([str(d)]) == 2


def test_archivo_explicito(tmp_path, modelo_ok):
    d = _config(tmp_path)
    assert cli.main([str(d), str(d / "evals" / "e.eval.yaml")]) == 0


def _romper_no_utf8(d):
    (d / "evals" / "e.eval.yaml").write_bytes(b"\xff\xfe\x00bad")


def _romper_cases_file(d):
    p = d / "evals" / "e.eval.yaml"
    doc = yaml.safe_load(p.read_text())
    doc["spec"]["cases_file"] = "c.jsonl"
    p.write_text(yaml.safe_dump(doc))
    (d / "evals" / "c.jsonl").write_bytes(b"\xff\xfe\x00bad")


def _romper_metadata(d):
    p = d / "evals" / "e.eval.yaml"
    doc = yaml.safe_load(p.read_text())
    doc["metadata"] = ["e"]
    p.write_text(yaml.safe_dump(doc))


def _romper_agente(d):
    (d / "agents" / "mala.agent.yaml").write_text("spec: [")


def _romper_raiz(d):
    p = d / "evals" / "e.eval.yaml"
    doc = yaml.safe_load(p.read_text())
    doc["extra"] = 1
    p.write_text(yaml.safe_dump(doc))


@pytest.mark.parametrize(
    "romper",
    [_romper_no_utf8, _romper_cases_file, _romper_metadata, _romper_agente, _romper_raiz],
)
def test_error_de_carga_sale_2_sin_correr(tmp_path, modelo_ok, monkeypatch, romper):
    corridos = []

    async def no_debe(*a, **kw):
        corridos.append(1)

    monkeypatch.setattr(cli, "correr_eval", no_debe)
    d = _config(tmp_path)
    romper(d)
    assert cli.main([str(d)]) == 2
    assert corridos == []
