"""Wizard presets for Orbit deployments."""

from __future__ import annotations

from typing import Any

PRESETS: dict[str, dict[str, Any]] = {
    "starter": {
        "estimated_cost": 30,
        "compute": {
            "runtime": {"min_instances": 1, "max_instances": 3, "cpu": "2", "memory": "2Gi"},
            "cloud_api": {"min_instances": 1, "max_instances": 2, "cpu": "1", "memory": "1Gi"},
            "studio": {"min_instances": 0, "max_instances": 1, "cpu": "1", "memory": "512Mi"},
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
    "pro": {
        "estimated_cost": 150,
        "compute": {
            "runtime": {"min_instances": 1, "max_instances": 5, "cpu": "4", "memory": "4Gi"},
            "cloud_api": {"min_instances": 1, "max_instances": 3, "cpu": "2", "memory": "2Gi"},
            "studio": {"min_instances": 1, "max_instances": 3, "cpu": "1", "memory": "1Gi"},
        },
        "database": {
            "tier": "db-g1-small",
            "version": "POSTGRES_16",
            "storage_gb": 20,
            "high_availability": True,
        },
        "cache": {"tier": "standard", "memory_gb": 4},
        "secrets": {"provider_keys": True, "jwt_secret": True},
        "images": {
            "runtime": "fulfarodev/astromesh:latest",
            "cloud_api": "fulfarodev/astromesh-cloud-api:latest",
            "studio": "fulfarodev/astromesh-cloud-studio:latest",
        },
    },
}


def build_orbit_yaml(
    *,
    name: str,
    environment: str,
    provider: str,
    project: str,
    region: str,
    preset: str,
) -> dict:
    """Build a complete orbit.yaml dict from wizard answers and a preset."""
    p = PRESETS[preset]
    return {
        "apiVersion": "astromesh/v1",
        "kind": "OrbitDeployment",
        "metadata": {"name": name, "environment": environment},
        "spec": {
            "provider": {"name": provider, "project": project, "region": region},
            "compute": p["compute"],
            "database": p["database"],
            "cache": p["cache"],
            "secrets": p["secrets"],
            "images": p["images"],
        },
    }
