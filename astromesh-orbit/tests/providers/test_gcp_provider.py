"""Tests for GCPProvider — template generation and protocol conformance."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from astromesh_orbit.config import OrbitConfig
from astromesh_orbit.core.provider import (
    ApplyResult,
    CheckResult,
    OrbitProvider,
    ValidationResult,
)
from astromesh_orbit.providers.gcp.provider import GCPProvider


@pytest.fixture
def provider():
    return GCPProvider()


@pytest.fixture
def config(sample_orbit_yaml: Path) -> OrbitConfig:
    return OrbitConfig.from_yaml(sample_orbit_yaml)


def test_gcp_provider_implements_protocol():
    """GCPProvider must satisfy OrbitProvider Protocol."""
    assert isinstance(GCPProvider(), OrbitProvider)


def test_gcp_provider_name():
    assert GCPProvider().name == "gcp"


async def test_generate_creates_tf_files(
    provider: GCPProvider, config: OrbitConfig, output_dir: Path
):
    files = await provider.generate(config, output_dir)
    assert len(files) >= 8
    names = [f.name for f in files]
    assert "main.tf" in names
    assert "cloud_run.tf" in names
    assert "cloud_sql.tf" in names
    assert "memorystore.tf" in names
    assert "secrets.tf" in names
    assert "iam.tf" in names
    assert "networking.tf" in names
    assert "outputs.tf" in names


async def test_generate_tf_files_are_valid_hcl(
    provider: GCPProvider, config: OrbitConfig, output_dir: Path
):
    """Generated files should contain valid-looking HCL (basic structural check)."""
    files = await provider.generate(config, output_dir)
    for f in files:
        content = f.read_text()
        assert len(content) > 0, f"{f.name} is empty"
        # Every .tf file should have at least one block
        assert any(
            kw in content for kw in ["resource", "variable", "output", "provider", "terraform"]
        ), f"{f.name} has no HCL blocks"


async def test_generate_includes_project_in_main_tf(
    provider: GCPProvider, config: OrbitConfig, output_dir: Path
):
    await provider.generate(config, output_dir)
    main_tf = (output_dir / "main.tf").read_text()
    assert "test-project-123" in main_tf


async def test_eject_writes_to_output_dir(
    provider: GCPProvider, config: OrbitConfig, tmp_path: Path
):
    eject_dir = tmp_path / "ejected"
    result = await provider.eject(config, eject_dir)
    assert result == eject_dir
    assert (eject_dir / "main.tf").exists()
    # Ejected files should have comments
    content = (eject_dir / "main.tf").read_text()
    assert "#" in content  # Should have explanatory comments
    # Should produce terraform.tfvars with resolved values
    tfvars = (eject_dir / "terraform.tfvars").read_text()
    assert "test-project-123" in tfvars
    assert "us-central1" in tfvars


async def test_validate_calls_all_checks(provider: GCPProvider, config: OrbitConfig):
    """Validate should run auth, project, and API checks."""
    with (
        patch(
            "astromesh_orbit.providers.gcp.provider.check_gcloud_auth", new_callable=AsyncMock
        ) as auth,
        patch(
            "astromesh_orbit.providers.gcp.provider.check_project", new_callable=AsyncMock
        ) as proj,
        patch(
            "astromesh_orbit.providers.gcp.provider.check_apis_enabled", new_callable=AsyncMock
        ) as apis,
    ):
        auth.return_value = CheckResult(name="auth", passed=True, message="ok")
        proj.return_value = CheckResult(name="project", passed=True, message="ok")
        apis.return_value = [CheckResult(name="api", passed=True, message="ok")]
        result = await provider.validate(config)
        assert result.ok is True
        auth.assert_called_once()
        proj.assert_called_once_with("test-project-123")


async def test_validate_fails_on_missing_auth(provider: GCPProvider, config: OrbitConfig):
    with (
        patch(
            "astromesh_orbit.providers.gcp.provider.check_gcloud_auth", new_callable=AsyncMock
        ) as auth,
        patch(
            "astromesh_orbit.providers.gcp.provider.check_project", new_callable=AsyncMock
        ) as proj,
        patch(
            "astromesh_orbit.providers.gcp.provider.check_apis_enabled", new_callable=AsyncMock
        ) as apis,
    ):
        auth.return_value = CheckResult(
            name="auth", passed=False, message="not authed", remediation="gcloud auth login"
        )
        proj.return_value = CheckResult(name="project", passed=True, message="ok")
        apis.return_value = []
        result = await provider.validate(config)
        assert result.ok is False


async def test_provision_orchestrates_full_flow(
    provider: GCPProvider, config: OrbitConfig, output_dir: Path
):
    """Provision should: validate -> ensure bucket -> generate -> init -> apply -> write env."""
    with (
        patch.object(provider, "validate", new_callable=AsyncMock) as mock_val,
        patch.object(provider, "generate", new_callable=AsyncMock) as mock_gen,
        patch(
            "astromesh_orbit.providers.gcp.provider.ensure_gcs_state_bucket",
            new_callable=AsyncMock,
        ) as mock_bucket,
        patch.object(provider._tf, "init", new_callable=AsyncMock),
        patch.object(provider._tf, "apply", new_callable=AsyncMock) as mock_apply,
    ):
        mock_val.return_value = ValidationResult(ok=True, checks=[])
        mock_gen.return_value = [output_dir / "main.tf"]
        mock_bucket.return_value = "test-bucket"
        mock_apply.return_value = ApplyResult(
            success=True,
            outputs={
                "runtime_url": "https://rt.run.app",
                "cloud_api_url": "https://api.run.app",
                "studio_url": "https://studio.run.app",
            },
            raw_output="Apply complete!",
        )
        result = await provider.provision(config, output_dir)
        assert result.endpoints["runtime"] == "https://rt.run.app"
        assert result.env_file.name == "orbit.env"
        mock_val.assert_called_once()
        mock_bucket.assert_called_once()
