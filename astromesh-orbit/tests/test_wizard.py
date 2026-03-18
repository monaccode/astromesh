"""Tests for wizard presets and orbit.yaml generation."""

from pathlib import Path

import yaml

from astromesh_orbit.wizard.defaults import PRESETS, build_orbit_yaml


def test_starter_preset_exists():
    assert "starter" in PRESETS
    preset = PRESETS["starter"]
    assert preset["estimated_cost"] == 30


def test_pro_preset_exists():
    assert "pro" in PRESETS
    preset = PRESETS["pro"]
    assert preset["estimated_cost"] == 150


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
        environment="dev",
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
        environment="dev",
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
