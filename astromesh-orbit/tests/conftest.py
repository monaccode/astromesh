"""Shared fixtures for Orbit tests."""

from pathlib import Path
import pytest
import yaml


SAMPLE_ORBIT_YAML = {
    "apiVersion": "astromesh/v1",
    "kind": "OrbitDeployment",
    "metadata": {"name": "test-astromesh", "environment": "dev"},
    "spec": {
        "provider": {"name": "gcp", "project": "test-project-123", "region": "us-central1"},
        "compute": {
            "runtime": {"min_instances": 1, "max_instances": 3, "cpu": "2", "memory": "2Gi"},
            "cloud_api": {"min_instances": 1, "max_instances": 2, "cpu": "1", "memory": "1Gi"},
            "studio": {"min_instances": 0, "max_instances": 1},
        },
        "database": {
            "tier": "db-f1-micro",
            "version": "POSTGRES_16",
            "storage_gb": 10,
            "high_availability": False,
        },
        "cache": {"tier": "basic", "memory_gb": 1},
        "secrets": {"provider_keys": True, "jwt_secret": True},
        "images": {
            "runtime": "fulfarodev/astromesh:latest",
            "cloud_api": "fulfarodev/astromesh-cloud-api:latest",
            "studio": "fulfarodev/astromesh-cloud-studio:latest",
        },
    },
}


@pytest.fixture
def sample_orbit_dict():
    import copy

    return copy.deepcopy(SAMPLE_ORBIT_YAML)


@pytest.fixture
def sample_orbit_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "orbit.yaml"
    path.write_text(yaml.dump(SAMPLE_ORBIT_YAML, default_flow_style=False))
    return path


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    d = tmp_path / "generated"
    d.mkdir()
    return d
