"""Tests for wizard presets and orbit.yaml generation."""

from pathlib import Path

import yaml

from astromesh_orbit.wizard.defaults import PRESETS, build_orbit_yaml


def test_starter_preset_exists():
    assert "starter" in PRESETS
    preset = PRESETS["starter"]
    assert preset["estimated_cost"] == 15


def test_pro_preset_exists():
    assert "pro" in PRESETS
    preset = PRESETS["pro"]
    assert preset["estimated_cost"] == 80


def test_starter_preset_values():
    p = PRESETS["starter"]
    assert p["compute"]["runtime"]["max_instances"] == 3
    assert p["database"]["high_availability"] is False
    assert p["cache"]["memory_gb"] == 1


def test_pro_preset_values():
    p = PRESETS["pro"]
    assert p["compute"]["runtime"]["max_instances"] == 5
    assert p["database"]["high_availability"] is True
    assert p["cache"]["memory_gb"] == 4


def test_build_orbit_yaml_starter():
    data = build_orbit_yaml(
        name="my-deploy",
        environment="develop",
        provider="gcp",
        project="my-project",
        region="us-central1",
        preset="starter",
    )
    assert data["apiVersion"] == "astromesh/v1"
    assert data["kind"] == "OrbitDeployment"
    assert data["metadata"]["name"] == "my-deploy"
    assert data["spec"]["provider"]["project"] == "my-project"
    assert data["spec"]["database"]["high_availability"] is False


def test_build_orbit_yaml_pro():
    data = build_orbit_yaml(
        name="prod-deploy",
        environment="production",
        provider="gcp",
        project="prod-project",
        region="europe-west1",
        preset="pro",
    )
    assert data["spec"]["database"]["high_availability"] is True
    assert data["spec"]["cache"]["memory_gb"] == 4
    assert data["metadata"]["environment"] == "production"


def test_build_orbit_yaml_writes_valid_yaml(tmp_path: Path):
    data = build_orbit_yaml(
        name="test",
        environment="develop",
        provider="gcp",
        project="test-proj",
        region="us-central1",
        preset="starter",
    )
    path = tmp_path / "orbit.yaml"
    path.write_text(yaml.dump(data, default_flow_style=False))
    loaded = yaml.safe_load(path.read_text())
    assert loaded["apiVersion"] == "astromesh/v1"

    # Verify it parses as valid OrbitConfig
    from astromesh_orbit.config import OrbitConfig

    config = OrbitConfig.from_yaml(path)
    assert config.spec.provider.name == "gcp"


def test_presets_include_storage():
    for name in ("starter", "pro"):
        storage = PRESETS[name]["storage"]
        assert storage["rag_documents"]["enabled"] is True
        assert storage["artifact_registry"]["enabled"] is True


def test_build_orbit_yaml_includes_storage():
    data = build_orbit_yaml(
        name="d",
        environment="develop",
        provider="gcp",
        project="p",
        region="us-central1",
        preset="starter",
    )
    assert data["spec"]["storage"]["rag_documents"]["enabled"] is True
    assert data["spec"]["storage"]["artifact_registry"]["enabled"] is True


def test_presets_include_observability():
    for name in ("starter", "pro"):
        obs = PRESETS[name]["observability"]
        assert obs["dashboard"] is True
        assert obs["tracing"]["enabled"] is False


def test_build_orbit_yaml_includes_observability():
    data = build_orbit_yaml(
        name="d",
        environment="develop",
        provider="gcp",
        project="p",
        region="us-central1",
        preset="starter",
    )
    assert data["spec"]["observability"]["dashboard"] is True
    assert data["spec"]["observability"]["tracing"]["enabled"] is False


def test_every_wizard_environment_choice_validates(monkeypatch, tmp_path):
    """The wizard offered `dev`, which OrbitMetadata rejects: its own default failed validation."""
    from astromesh_orbit.config import OrbitConfig
    from astromesh_orbit.wizard import interactive

    asked = {}

    def fake_ask(prompt, choices=None, default=None, **kw):
        if "Environment" in prompt:
            asked["choices"], asked["default"] = choices, default
        return default if default is not None else (choices[0] if choices else "p")

    monkeypatch.setattr(interactive.Prompt, "ask", staticmethod(fake_ask))
    monkeypatch.chdir(tmp_path)
    interactive.run_wizard(tmp_path / "orbit.yaml")

    assert asked["default"] in asked["choices"]
    for env in asked["choices"]:
        data = build_orbit_yaml(
            name="x",
            environment=env,
            provider="gcp",
            project="p",
            region="us-central1",
            preset="starter",
        )
        OrbitConfig(**data)  # raises on an environment the model rejects
