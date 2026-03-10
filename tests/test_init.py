"""Tests for the astromesh init wizard (cli/commands/init.py)."""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = PROJECT_ROOT / "config" / "profiles"
SAMPLE_AGENTS_DIR = PROJECT_ROOT / "config" / "agents"


def _make_config_dir(tmp_path: Path) -> Path:
    """Return a clean config directory inside tmp_path."""
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    return cfg


def _run_wizard(config_dir: Path, *, role=None, non_interactive=False, dev=False, prompts=None, confirms=None, mock_httpx=True):
    """Helper to run the init wizard with common mocks."""
    from cli.commands.init import init_command

    patches = [
        patch("cli.commands.init._detect_config_dir", return_value=(config_dir, "dev")),
    ]
    if prompts is not None:
        patches.append(patch("cli.commands.init.Prompt.ask", side_effect=prompts))
    if confirms is not None:
        patches.append(patch("cli.commands.init.Confirm.ask", side_effect=confirms))
    if mock_httpx:
        patches.append(patch("cli.commands.init.httpx.get", side_effect=Exception("mocked")))

    [p.__enter__() for p in patches]
    try:
        init_command(role=role, non_interactive=non_interactive, dev=dev)
    finally:
        for p in reversed(patches):
            p.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# 1. Profile copy — selected profile matches source
# ---------------------------------------------------------------------------

class TestProfileCopy:
    def test_profile_copy(self, tmp_path):
        config_dir = _make_config_dir(tmp_path)
        # Prompt.ask: first call = role selection ("full"), second = provider ("ollama")
        _run_wizard(config_dir, prompts=["full", "ollama"], confirms=[])

        runtime_yaml = config_dir / "runtime.yaml"
        assert runtime_yaml.exists(), "runtime.yaml was not created"

        written = yaml.safe_load(runtime_yaml.read_text())
        source = yaml.safe_load((PROFILES_DIR / "full.yaml").read_text())
        assert written == source


# ---------------------------------------------------------------------------
# 2. Provider — Ollama generates valid providers.yaml
# ---------------------------------------------------------------------------

class TestProviderOllama:
    def test_provider_ollama(self, tmp_path):
        config_dir = _make_config_dir(tmp_path)
        _run_wizard(config_dir, prompts=["full", "ollama"], confirms=[])

        providers_yaml = config_dir / "providers.yaml"
        assert providers_yaml.exists()

        data = yaml.safe_load(providers_yaml.read_text())
        # Nested dict structure: spec.providers.ollama
        ollama = data["spec"]["providers"]["ollama"]
        assert ollama["type"] == "ollama"
        assert "endpoint" in ollama
        assert "models" in ollama


# ---------------------------------------------------------------------------
# 3. Provider — OpenAI references env var
# ---------------------------------------------------------------------------

class TestProviderOpenAI:
    def test_provider_openai(self, tmp_path):
        config_dir = _make_config_dir(tmp_path)
        # Prompts: role, provider, api_key
        _run_wizard(config_dir, prompts=["full", "openai", "sk-test-key-12345"], confirms=[])

        providers_yaml = config_dir / "providers.yaml"
        assert providers_yaml.exists()

        data = yaml.safe_load(providers_yaml.read_text())
        assert "openai" in data["spec"]["providers"]
        openai_cfg = data["spec"]["providers"]["openai"]
        # Config should have models but key goes to .env, not in YAML
        assert "models" in openai_cfg


# ---------------------------------------------------------------------------
# 4. Provider — Anthropic references env var
# ---------------------------------------------------------------------------

class TestProviderAnthropic:
    def test_provider_anthropic(self, tmp_path):
        config_dir = _make_config_dir(tmp_path)
        _run_wizard(config_dir, prompts=["full", "anthropic", "sk-ant-test"], confirms=[])

        providers_yaml = config_dir / "providers.yaml"
        assert providers_yaml.exists()

        data = yaml.safe_load(providers_yaml.read_text())
        assert "anthropic" in data["spec"]["providers"]


# ---------------------------------------------------------------------------
# 5. .env file written with API key
# ---------------------------------------------------------------------------

class TestEnvFileWritten:
    def test_env_file_written(self, tmp_path):
        config_dir = _make_config_dir(tmp_path)
        _run_wizard(config_dir, prompts=["full", "openai", "sk-test-key-12345"], confirms=[])

        # .env is written to parent of config_dir (since config_dir.name == "config")
        env_file = config_dir.parent / ".env"
        if not env_file.exists():
            env_file = config_dir / ".env"

        assert env_file.exists(), ".env file was not created"
        contents = env_file.read_text()
        assert "OPENAI_API_KEY=sk-test-key-12345" in contents


# ---------------------------------------------------------------------------
# 6. Idempotency — existing config not overwritten when user declines
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_idempotency(self, tmp_path):
        from click.exceptions import Exit as ClickExit
        from cli.commands.init import init_command

        config_dir = _make_config_dir(tmp_path)

        # Pre-populate runtime.yaml
        original_content = "# original content\napiVersion: astromesh/v1\n"
        runtime_yaml = config_dir / "runtime.yaml"
        runtime_yaml.write_text(original_content)

        # Confirm.ask returns False (user declines reconfigure) → typer.Exit(0) → click.Exit
        with (
            patch("cli.commands.init._detect_config_dir", return_value=(config_dir, "dev")),
            patch("cli.commands.init.Confirm.ask", return_value=False),
            pytest.raises(ClickExit),
        ):
            init_command(role=None, non_interactive=False, dev=False)

        assert runtime_yaml.read_text() == original_content


# ---------------------------------------------------------------------------
# 7. Non-interactive — no prompts, defaults to full + ollama
# ---------------------------------------------------------------------------

class TestNonInteractive:
    def test_non_interactive(self, tmp_path):
        from cli.commands.init import init_command

        config_dir = _make_config_dir(tmp_path)

        with (
            patch("cli.commands.init._detect_config_dir", return_value=(config_dir, "dev")),
            patch("cli.commands.init.Prompt.ask") as mock_prompt,
            patch("cli.commands.init.Confirm.ask") as mock_confirm,
        ):
            init_command(role=None, non_interactive=True, dev=False)
            mock_prompt.assert_not_called()
            mock_confirm.assert_not_called()

        runtime_yaml = config_dir / "runtime.yaml"
        assert runtime_yaml.exists()

        data = yaml.safe_load(runtime_yaml.read_text())
        assert data.get("metadata", {}).get("name") == "full"

        providers_yaml = config_dir / "providers.yaml"
        assert providers_yaml.exists()

        pdata = yaml.safe_load(providers_yaml.read_text())
        assert "ollama" in pdata["spec"]["providers"]


# ---------------------------------------------------------------------------
# 8. Validation — generated YAML is valid
# ---------------------------------------------------------------------------

class TestValidationRuns:
    def test_validation_runs(self, tmp_path):
        config_dir = _make_config_dir(tmp_path)
        _run_wizard(config_dir, prompts=["full", "ollama"], confirms=[])

        for yaml_file in config_dir.glob("*.yaml"):
            parsed = yaml.safe_load(yaml_file.read_text())
            assert parsed is not None, f"{yaml_file.name} parsed as None"
            assert isinstance(parsed, dict), f"{yaml_file.name} is not a mapping"

        runtime = yaml.safe_load((config_dir / "runtime.yaml").read_text())
        assert runtime["apiVersion"] == "astromesh/v1"
        assert runtime["kind"] == "RuntimeConfig"


# ---------------------------------------------------------------------------
# 9. --dev flag uses ./config/ directory
# ---------------------------------------------------------------------------

class TestDevModeConfigDir:
    def test_dev_mode_config_dir(self):
        from cli.commands.init import _detect_config_dir

        config_dir, mode = _detect_config_dir(dev=True)
        assert config_dir == Path("./config")
        assert mode == "dev"


# ---------------------------------------------------------------------------
# 10. agents/ directory created with sample agents
# ---------------------------------------------------------------------------

class TestAgentsDirCreated:
    def test_agents_dir_created(self, tmp_path):
        config_dir = _make_config_dir(tmp_path)
        _run_wizard(config_dir, prompts=["full", "ollama"], confirms=[])

        agents_dir = config_dir / "agents"
        assert agents_dir.exists()
        assert agents_dir.is_dir()

        agent_files = list(agents_dir.glob("*.agent.yaml"))
        assert len(agent_files) > 0, "No sample agents copied"

        for af in agent_files:
            data = yaml.safe_load(af.read_text())
            assert data["apiVersion"] == "astromesh/v1"
            assert data["kind"] == "Agent"
