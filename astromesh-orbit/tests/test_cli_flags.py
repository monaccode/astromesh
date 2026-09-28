"""orbit init --provider/--preset y orbit apply --auto-approve hacen lo que dicen."""

from types import SimpleNamespace

from typer.testing import CliRunner

from astromesh_orbit import cli

runner = CliRunner()


def test_init_passes_provider_and_preset_to_the_wizard(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "run_wizard", lambda **kw: seen.update(kw))
    result = runner.invoke(cli.orbit_app, ["init", "--provider", "gcp", "--preset", "pro"])
    assert result.exit_code == 0, result.output
    assert seen == {"provider": "gcp", "preset": "pro"}


def test_wizard_skips_the_prompts_it_was_given(monkeypatch, tmp_path):
    from astromesh_orbit.wizard import interactive

    asked = []

    def fake_ask(prompt, choices=None, default=None, **kw):
        asked.append(prompt.strip())
        return default if default is not None else (choices[0] if choices else "p")

    monkeypatch.setattr(interactive.Prompt, "ask", staticmethod(fake_ask))
    monkeypatch.chdir(tmp_path)
    interactive.run_wizard(tmp_path / "orbit.yaml", provider="gcp", preset="pro")
    assert not any(p.startswith(("Cloud provider", "Preset")) for p in asked)
    assert "preset" not in (tmp_path / "orbit.yaml").read_text()  # the preset expands to sizes
    import yaml

    data = yaml.safe_load((tmp_path / "orbit.yaml").read_text())
    from astromesh_orbit.wizard.defaults import PRESETS

    assert data["spec"]["database"] == PRESETS["pro"]["database"]


def test_init_rejects_an_unknown_preset(monkeypatch):
    monkeypatch.setattr(cli, "run_wizard", lambda **kw: None)
    result = runner.invoke(cli.orbit_app, ["init", "--preset", "enterprise"])
    assert result.exit_code != 0


def _fake_apply(monkeypatch):
    provisioned = []

    class Prov:
        async def provision(self, cfg, out):
            provisioned.append(True)
            return SimpleNamespace(endpoints={}, env_file="x.env")

    monkeypatch.setattr(
        cli,
        "_load_config",
        lambda path: SimpleNamespace(
            metadata=SimpleNamespace(name="demo"),
            spec=SimpleNamespace(provider=SimpleNamespace(project="p", region="r")),
        ),
    )
    monkeypatch.setattr(cli, "_get_provider", lambda cfg: Prov())
    return provisioned


def test_apply_asks_before_deploying_and_stops_on_no(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    provisioned = _fake_apply(monkeypatch)
    result = runner.invoke(cli.orbit_app, ["apply"], input="n\n")
    assert result.exit_code != 0
    assert provisioned == []


def test_apply_auto_approve_deploys_without_asking(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    provisioned = _fake_apply(monkeypatch)
    result = runner.invoke(cli.orbit_app, ["apply", "--auto-approve"])
    assert result.exit_code == 0, result.output
    assert provisioned == [True]
