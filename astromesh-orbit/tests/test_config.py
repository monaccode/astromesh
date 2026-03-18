"""Tests for OrbitConfig parsing."""

from pathlib import Path
import pytest
import yaml

from astromesh_orbit.config import OrbitConfig


def test_parse_valid_yaml(sample_orbit_yaml: Path):
    config = OrbitConfig.from_yaml(sample_orbit_yaml)
    assert config.metadata.name == "test-astromesh"
    assert config.spec.provider.name == "gcp"
    assert config.spec.provider.project == "test-project-123"
    assert config.spec.provider.region == "us-central1"


def test_parse_compute_specs(sample_orbit_yaml: Path):
    config = OrbitConfig.from_yaml(sample_orbit_yaml)
    assert config.spec.compute.runtime.cpu == "2"
    assert config.spec.compute.runtime.max_instances == 3
    assert config.spec.compute.studio.min_instances == 0


def test_parse_database_spec(sample_orbit_yaml: Path):
    config = OrbitConfig.from_yaml(sample_orbit_yaml)
    assert config.spec.database.tier == "db-f1-micro"
    assert config.spec.database.version == "POSTGRES_16"
    assert config.spec.database.high_availability is False


def test_parse_cache_spec(sample_orbit_yaml: Path):
    config = OrbitConfig.from_yaml(sample_orbit_yaml)
    assert config.spec.cache.tier == "basic"
    assert config.spec.cache.memory_gb == 1


def test_parse_secrets_spec(sample_orbit_yaml: Path):
    config = OrbitConfig.from_yaml(sample_orbit_yaml)
    assert config.spec.secrets.provider_keys is True
    assert config.spec.secrets.jwt_secret is True


def test_parse_images(sample_orbit_yaml: Path):
    config = OrbitConfig.from_yaml(sample_orbit_yaml)
    assert "astromesh" in config.spec.images.runtime


def test_invalid_api_version(tmp_path: Path):
    data = {
        "apiVersion": "wrong/v2",
        "kind": "OrbitDeployment",
        "metadata": {"name": "x"},
        "spec": {"provider": {"name": "gcp", "project": "p", "region": "us-central1"}},
    }
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.dump(data))
    with pytest.raises(ValueError, match="apiVersion"):
        OrbitConfig.from_yaml(path)


def test_invalid_kind(tmp_path: Path):
    data = {
        "apiVersion": "astromesh/v1",
        "kind": "Wrong",
        "metadata": {"name": "x"},
        "spec": {"provider": {"name": "gcp", "project": "p", "region": "us-central1"}},
    }
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.dump(data))
    with pytest.raises(ValueError, match="kind"):
        OrbitConfig.from_yaml(path)


def test_missing_provider(tmp_path: Path):
    data = {
        "apiVersion": "astromesh/v1",
        "kind": "OrbitDeployment",
        "metadata": {"name": "x", "environment": "dev"},
        "spec": {"compute": {}, "database": {}, "cache": {}, "secrets": {}, "images": {}},
    }
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.dump(data))
    with pytest.raises(Exception):  # Pydantic ValidationError
        OrbitConfig.from_yaml(path)


def test_default_environment(tmp_path: Path, sample_orbit_dict: dict):
    del sample_orbit_dict["metadata"]["environment"]
    path = tmp_path / "orbit.yaml"
    path.write_text(yaml.dump(sample_orbit_dict))
    config = OrbitConfig.from_yaml(path)
    assert config.metadata.environment == "dev"


def test_file_not_found():
    with pytest.raises(FileNotFoundError):
        OrbitConfig.from_yaml(Path("/nonexistent/orbit.yaml"))
