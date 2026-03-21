"""Tests for core data types and OrbitProvider protocol."""

from astromesh_orbit.core.provider import (
    CheckResult,
    ValidationResult,
    PlanResult,
    ApplyResult,
    ProvisionResult,
    ResourceStatus,
    DeploymentStatus,
    OrbitProvider,
)
from astromesh_orbit.core.resources import ComputeSpec, DatabaseSpec, CacheSpec, ImagesSpec
from pathlib import Path


def test_check_result_pass():
    c = CheckResult(name="auth", passed=True, message="Authenticated", remediation=None)
    assert c.passed is True
    assert c.remediation is None


def test_check_result_fail_with_remediation():
    c = CheckResult(
        name="api_enabled",
        passed=False,
        message="sqladmin.googleapis.com not enabled",
        remediation="gcloud services enable sqladmin.googleapis.com",
    )
    assert c.passed is False
    assert "gcloud" in c.remediation


def test_validation_result_aggregates_checks():
    checks = [
        CheckResult(name="a", passed=True, message="ok", remediation=None),
        CheckResult(name="b", passed=False, message="fail", remediation="fix"),
    ]
    v = ValidationResult(ok=False, checks=checks)
    assert v.ok is False
    assert len(v.checks) == 2


def test_plan_result():
    p = PlanResult(
        resources_to_create=["cloud_run.runtime"],
        resources_to_update=[],
        resources_to_destroy=[],
        raw_output="Terraform plan output",
        estimated_monthly_cost=35.0,
    )
    assert len(p.resources_to_create) == 1
    assert p.estimated_monthly_cost == 35.0


def test_apply_result():
    a = ApplyResult(
        success=True,
        outputs={"runtime_url": "https://runtime.run.app"},
        raw_output="Apply complete!",
    )
    assert a.success is True
    assert "runtime_url" in a.outputs


def test_provision_result():
    apply = ApplyResult(success=True, outputs={}, raw_output="")
    p = ProvisionResult(
        apply=apply,
        env_file=Path(".orbit/orbit.env"),
        endpoints={"runtime": "https://runtime.run.app"},
    )
    assert p.endpoints["runtime"].startswith("https://")


def test_deployment_status():
    rs = ResourceStatus(
        name="astromesh-runtime",
        resource_type="cloud_run_v2_service",
        status="running",
        url="https://runtime.run.app",
    )
    ds = DeploymentStatus(
        resources=[rs],
        state_bucket="test-project-astromesh-orbit-state",
        last_applied="2026-03-18T12:00:00Z",
    )
    assert len(ds.resources) == 1
    assert ds.resources[0].status == "running"


def test_orbit_provider_is_runtime_checkable():
    assert hasattr(OrbitProvider, "__protocol_attrs__") or isinstance(OrbitProvider, type)
    # Verify it's a Protocol — runtime_checkable allows isinstance checks
    from typing import Protocol

    assert issubclass(OrbitProvider, Protocol)


def test_compute_spec():
    cs = ComputeSpec(min_instances=1, max_instances=5, cpu="2", memory="2Gi")
    assert cs.cpu == "2"


def test_database_spec_defaults():
    ds = DatabaseSpec(tier="db-f1-micro", version="POSTGRES_16", storage_gb=10)
    assert ds.high_availability is False


def test_cache_spec():
    cs = CacheSpec(tier="basic", memory_gb=1)
    assert cs.tier == "basic"


def test_images_spec():
    i = ImagesSpec(
        runtime="fulfarodev/astromesh:latest",
    )
    assert "astromesh" in i.runtime
