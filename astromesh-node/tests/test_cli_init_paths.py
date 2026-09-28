"""astromeshctl init: perfiles y config dir que existen en una instalación empaquetada."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import typer

from astromesh_node.cli.commands import init as init_cmd


def test_bundled_config_has_the_profiles_and_sample_agents():
    config = init_cmd.bundled_config_dir()
    assert config is not None
    assert (config / "profiles" / "full.yaml").is_file()
    assert any((config / "agents").glob("*.agent.yaml"))


def test_bundled_config_prefers_the_wheel_layout(tmp_path, monkeypatch):
    """Instalado (.deb/.rpm/macOS/Windows), el core trae su config en astromesh/_bundled/config."""
    import astromesh

    pkg = tmp_path / "site-packages" / "astromesh"
    (pkg / "_bundled" / "config" / "profiles").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    monkeypatch.setattr(astromesh, "__file__", str(pkg / "__init__.py"))
    assert init_cmd.bundled_config_dir() == (pkg / "_bundled" / "config").resolve()


def test_system_mode_uses_the_platform_config_dir(tmp_path, monkeypatch):
    """Como admin, macOS y Windows tienen su propio config dir: no es /etc/astromesh."""
    monkeypatch.setattr(init_cmd, "_is_admin", lambda: True)
    monkeypatch.setattr(
        init_cmd, "get_installer", lambda: SimpleNamespace(config_dir=lambda: tmp_path / "cfg")
    )
    assert init_cmd._detect_config_dir(dev=False) == (tmp_path / "cfg", "system")


def test_dev_mode_without_admin(monkeypatch):
    monkeypatch.setattr(init_cmd, "_is_admin", lambda: False)
    assert init_cmd._detect_config_dir(dev=False) == (Path("./config"), "dev")


def test_a_missing_profile_aborts_instead_of_writing_an_empty_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(init_cmd, "bundled_config_dir", lambda: tmp_path / "nothing")
    with pytest.raises(typer.Exit) as exc:
        init_cmd._write_configs(tmp_path / "out", "full", None, None)
    assert exc.value.exit_code == 1
    assert not (tmp_path / "out" / "runtime.yaml").exists()
