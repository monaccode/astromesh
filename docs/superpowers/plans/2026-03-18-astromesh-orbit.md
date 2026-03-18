# Astromesh Orbit Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `astromesh-orbit`, a standalone subproject that deploys the full Astromesh stack to GCP using managed cloud-native services via generated Terraform.

**Architecture:** Provider plugin pattern — `OrbitProvider` Protocol implemented per cloud. Each provider generates Terraform HCL from Jinja2 templates. A thin `TerraformRunner` wrapper executes `terraform` as subprocess. CLI integrates into `astromeshctl` via Python entry points plugin discovery.

**Tech Stack:** Python 3.12, Typer, Rich, Jinja2, Pydantic v2, PyYAML, Terraform (external binary), google-cloud-resource-manager, google-auth, hatchling, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-03-18-astromesh-orbit-design.md`

---

## File Structure

### New files (astromesh-orbit/)

| File | Responsibility |
|---|---|
| `astromesh-orbit/pyproject.toml` | Package config, entry points, tool config |
| `astromesh-orbit/astromesh_orbit/__init__.py` | Package version |
| `astromesh-orbit/astromesh_orbit/config.py` | `OrbitConfig` — Pydantic model parsing `orbit.yaml` |
| `astromesh-orbit/astromesh_orbit/core/provider.py` | `OrbitProvider` Protocol + all dataclasses (result types) |
| `astromesh-orbit/astromesh_orbit/core/resources.py` | `ComputeSpec`, `DatabaseSpec`, `CacheSpec`, `SecretsSpec`, `ImagesSpec` dataclasses |
| `astromesh-orbit/astromesh_orbit/terraform/runner.py` | `TerraformRunner` — subprocess wrapper for terraform CLI |
| `astromesh-orbit/astromesh_orbit/terraform/backend.py` | State bucket creation via GCP SDK |
| `astromesh-orbit/astromesh_orbit/wizard/defaults.py` | Starter/Pro preset definitions |
| `astromesh-orbit/astromesh_orbit/wizard/interactive.py` | Typer/Rich wizard prompts |
| `astromesh-orbit/astromesh_orbit/providers/gcp/__init__.py` | GCP provider exports |
| `astromesh-orbit/astromesh_orbit/providers/gcp/provider.py` | `GCPProvider(OrbitProvider)` implementation |
| `astromesh-orbit/astromesh_orbit/providers/gcp/validators.py` | GCP pre-deploy validation (project, APIs, perms) |
| `astromesh-orbit/astromesh_orbit/providers/gcp/templates/*.tf.j2` | 10 Jinja2 Terraform templates |
| `astromesh-orbit/astromesh_orbit/cli.py` | `register(app)` function + orbit subcommands |
| `astromesh-orbit/tests/test_config.py` | OrbitConfig parsing tests |
| `astromesh-orbit/tests/test_terraform_runner.py` | TerraformRunner tests (mocked subprocess) |
| `astromesh-orbit/tests/test_wizard.py` | Wizard defaults and preset tests |
| `astromesh-orbit/tests/providers/test_gcp_provider.py` | GCP template generation + snapshot tests |
| `astromesh-orbit/tests/conftest.py` | Shared fixtures (sample orbit.yaml, tmp dirs) |
| `astromesh-orbit/docs/roadmap.md` | Service roadmap |

### Modified files (core astromesh)

| File | Change |
|---|---|
| `cli/main.py` | Add plugin discovery via `importlib.metadata.entry_points` |
| `.gitignore` | Add `.orbit/` entry |

---

## Task 1: Scaffold subproject and pyproject.toml

**Files:**
- Create: `astromesh-orbit/pyproject.toml`
- Create: `astromesh-orbit/astromesh_orbit/__init__.py`
- Create: `astromesh-orbit/tests/__init__.py`
- Create: `astromesh-orbit/tests/conftest.py`
- Create: `astromesh-orbit/docs/roadmap.md`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "astromesh-orbit"
version = "0.1.0"
description = "Cloud-native deployment for Astromesh — provision infrastructure on any cloud"
requires-python = ">=3.12"
license = {text = "Apache-2.0"}
dependencies = [
    "jinja2>=3.1",
    "pyyaml>=6.0",
    "pydantic>=2.0",
    "rich>=13.0",
    "typer>=0.12",
]

[project.optional-dependencies]
gcp = [
    "google-cloud-resource-manager>=1.12",
    "google-auth>=2.29",
]
aws = []
azure = []
all = ["astromesh-orbit[gcp]"]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
]

[project.entry-points."astromeshctl.plugins"]
orbit = "astromesh_orbit.cli:register"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["astromesh_orbit"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "orbit_gcp: tests that create real GCP resources (deselect with -m 'not orbit_gcp')",
]
```

- [ ] **Step 2: Create `__init__.py`**

```python
"""Astromesh Orbit — Cloud-native deployment for Astromesh."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Create empty test package**

Create `astromesh-orbit/tests/__init__.py` (empty).

Create `astromesh-orbit/tests/conftest.py`:

```python
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
```

- [ ] **Step 4: Create `docs/roadmap.md`**

Copy the roadmap from the spec (v0.1.0 through v1.0.0).

- [ ] **Step 5: Verify project scaffolding**

Run: `cd astromesh-orbit && uv sync --extra dev`
Expected: Dependencies install successfully.

- [ ] **Step 6: Commit**

```bash
git add astromesh-orbit/
git commit -m "feat(orbit): scaffold astromesh-orbit subproject with pyproject.toml and test fixtures"
```

---

## Task 2: Core data types — Provider Protocol and resource specs

**Files:**
- Create: `astromesh-orbit/astromesh_orbit/core/__init__.py`
- Create: `astromesh-orbit/astromesh_orbit/core/provider.py`
- Create: `astromesh-orbit/astromesh_orbit/core/resources.py`
- Test: `astromesh-orbit/tests/test_core.py`

- [ ] **Step 1: Write tests for data types**

Create `astromesh-orbit/tests/test_core.py`:

```python
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
from astromesh_orbit.core.resources import ComputeSpec, DatabaseSpec, CacheSpec, SecretsSpec, ImagesSpec
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
    from typing import runtime_checkable, Protocol
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
        cloud_api="fulfarodev/astromesh-cloud-api:latest",
        studio="fulfarodev/astromesh-cloud-studio:latest",
    )
    assert "astromesh" in i.runtime
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd astromesh-orbit && uv run pytest tests/test_core.py -v`
Expected: ImportError — modules don't exist yet.

- [ ] **Step 3: Implement `core/resources.py`**

```python
"""Typed resource specifications for Orbit deployments."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ComputeSpec:
    min_instances: int = 1
    max_instances: int = 3
    cpu: str = "1"
    memory: str = "1Gi"


@dataclass(frozen=True)
class DatabaseSpec:
    tier: str = "db-f1-micro"
    version: str = "POSTGRES_16"
    storage_gb: int = 10
    high_availability: bool = False


@dataclass(frozen=True)
class CacheSpec:
    tier: str = "basic"
    memory_gb: int = 1


@dataclass(frozen=True)
class SecretsSpec:
    provider_keys: bool = True
    jwt_secret: bool = True


@dataclass(frozen=True)
class ImagesSpec:
    runtime: str = "fulfarodev/astromesh:latest"
    cloud_api: str = "fulfarodev/astromesh-cloud-api:latest"
    studio: str = "fulfarodev/astromesh-cloud-studio:latest"
```

- [ ] **Step 4: Implement `core/provider.py`**

```python
"""OrbitProvider Protocol and result data types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from astromesh_orbit.config import OrbitConfig


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    remediation: str | None = None


@dataclass
class ValidationResult:
    ok: bool
    checks: list[CheckResult]


@dataclass
class PlanResult:
    resources_to_create: list[str]
    resources_to_update: list[str]
    resources_to_destroy: list[str]
    raw_output: str
    estimated_monthly_cost: float | None = None


@dataclass
class ApplyResult:
    success: bool
    outputs: dict[str, str]
    raw_output: str


@dataclass
class ProvisionResult:
    apply: ApplyResult
    env_file: Path
    endpoints: dict[str, str]


@dataclass
class ResourceStatus:
    name: str
    resource_type: str
    status: str  # "running", "stopped", "error", "not_found"
    url: str | None = None


@dataclass
class DeploymentStatus:
    resources: list[ResourceStatus]
    state_bucket: str
    last_applied: str | None = None


@runtime_checkable
class OrbitProvider(Protocol):
    name: str

    async def validate(self, config: OrbitConfig) -> ValidationResult: ...
    async def generate(self, config: OrbitConfig, output_dir: Path) -> list[Path]: ...
    async def provision(self, config: OrbitConfig, output_dir: Path) -> ProvisionResult: ...
    async def status(self, config: OrbitConfig) -> DeploymentStatus: ...
    async def destroy(self, config: OrbitConfig, output_dir: Path) -> None: ...
    async def eject(self, config: OrbitConfig, output_dir: Path) -> Path: ...
```

Create `astromesh-orbit/astromesh_orbit/core/__init__.py` (empty).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd astromesh-orbit && uv run pytest tests/test_core.py -v`
Expected: All 12 tests PASS.

Note: `core/provider.py` imports `OrbitConfig` which doesn't exist yet. To avoid circular imports, use `from __future__ import annotations` (already included) — the type reference is string-only at runtime. The tests import the dataclasses directly and don't trigger the forward reference. If the import fails, temporarily replace the import with `OrbitConfig = object` or use `TYPE_CHECKING`. This will be resolved in Task 3 when `config.py` is created.

- [ ] **Step 6: Commit**

```bash
git add astromesh-orbit/astromesh_orbit/core/ astromesh-orbit/tests/test_core.py
git commit -m "feat(orbit): add OrbitProvider Protocol and resource spec dataclasses"
```

---

## Task 3: OrbitConfig — Pydantic model for orbit.yaml

**Files:**
- Create: `astromesh-orbit/astromesh_orbit/config.py`
- Test: `astromesh-orbit/tests/test_config.py`

- [ ] **Step 1: Write tests**

Create `astromesh-orbit/tests/test_config.py`:

```python
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
    data = {"apiVersion": "wrong/v2", "kind": "OrbitDeployment", "metadata": {"name": "x"}, "spec": {}}
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.dump(data))
    with pytest.raises(ValueError, match="apiVersion"):
        OrbitConfig.from_yaml(path)


def test_invalid_kind(tmp_path: Path):
    data = {"apiVersion": "astromesh/v1", "kind": "Wrong", "metadata": {"name": "x"}, "spec": {}}
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd astromesh-orbit && uv run pytest tests/test_config.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `config.py`**

```python
"""OrbitConfig — Pydantic model for orbit.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator


class ProviderSpec(BaseModel):
    name: Literal["gcp", "aws", "azure"]
    project: str = ""
    region: str = "us-central1"


class ComputeServiceSpec(BaseModel):
    min_instances: int = 1
    max_instances: int = 3
    cpu: str = "1"
    memory: str = "1Gi"


class ComputeSpec(BaseModel):
    runtime: ComputeServiceSpec = ComputeServiceSpec(cpu="2", memory="2Gi", max_instances=5)
    cloud_api: ComputeServiceSpec = ComputeServiceSpec()
    studio: ComputeServiceSpec = ComputeServiceSpec(min_instances=0, max_instances=2)


class DatabaseSpec(BaseModel):
    tier: str = "db-f1-micro"
    version: str = "POSTGRES_16"
    storage_gb: int = 10
    high_availability: bool = False


class CacheSpec(BaseModel):
    tier: str = "basic"
    memory_gb: int = 1


class SecretsSpec(BaseModel):
    provider_keys: bool = True
    jwt_secret: bool = True


class ImagesSpec(BaseModel):
    runtime: str = "fulfarodev/astromesh:latest"
    cloud_api: str = "fulfarodev/astromesh-cloud-api:latest"
    studio: str = "fulfarodev/astromesh-cloud-studio:latest"


class OrbitSpec(BaseModel):
    provider: ProviderSpec
    compute: ComputeSpec = ComputeSpec()
    database: DatabaseSpec = DatabaseSpec()
    cache: CacheSpec = CacheSpec()
    secrets: SecretsSpec = SecretsSpec()
    images: ImagesSpec = ImagesSpec()


class OrbitMetadata(BaseModel):
    name: str
    environment: Literal["dev", "staging", "production"] = "dev"


class OrbitConfig(BaseModel):
    apiVersion: str
    kind: str
    metadata: OrbitMetadata
    spec: OrbitSpec

    @model_validator(mode="after")
    def validate_schema(self) -> OrbitConfig:
        if self.apiVersion != "astromesh/v1":
            raise ValueError(f"Unsupported apiVersion: {self.apiVersion}. Expected: astromesh/v1")
        if self.kind != "OrbitDeployment":
            raise ValueError(f"Unsupported kind: {self.kind}. Expected: OrbitDeployment")
        return self

    @classmethod
    def from_yaml(cls, path: Path) -> OrbitConfig:
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        data = yaml.safe_load(path.read_text())
        return cls.model_validate(data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd astromesh-orbit && uv run pytest tests/test_config.py -v`
Expected: All 11 tests PASS.

- [ ] **Step 5: Verify core/provider.py import resolves**

Run: `cd astromesh-orbit && uv run python -c "from astromesh_orbit.core.provider import OrbitProvider; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add astromesh-orbit/astromesh_orbit/config.py astromesh-orbit/tests/test_config.py
git commit -m "feat(orbit): add OrbitConfig Pydantic model with YAML parsing and validation"
```

---

## Task 4: TerraformRunner — subprocess wrapper

**Files:**
- Create: `astromesh-orbit/astromesh_orbit/terraform/__init__.py`
- Create: `astromesh-orbit/astromesh_orbit/terraform/runner.py`
- Test: `astromesh-orbit/tests/test_terraform_runner.py`

- [ ] **Step 1: Write tests**

Create `astromesh-orbit/tests/test_terraform_runner.py`:

```python
"""Tests for TerraformRunner — mocked subprocess calls."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from astromesh_orbit.terraform.runner import TerraformRunner, TerraformNotFoundError


@pytest.fixture
def runner():
    return TerraformRunner()


async def test_check_installed_success(runner: TerraformRunner):
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, json.dumps({"terraform_version": "1.9.0"}), "")
        version = await runner.check_installed()
        assert version == "1.9.0"


async def test_check_installed_not_found(runner: TerraformRunner):
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = FileNotFoundError
        with pytest.raises(TerraformNotFoundError):
            await runner.check_installed()


async def test_init_calls_terraform(runner: TerraformRunner, tmp_path: Path):
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, "Terraform has been successfully initialized!", "")
        await runner.init(tmp_path)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[:2] == ["terraform", "init"]


async def test_plan_parses_output(runner: TerraformRunner, tmp_path: Path):
    plan_output = (
        "Plan: 8 to add, 0 to change, 0 to destroy.\n"
        "\n"
        "  + google_cloud_run_v2_service.runtime\n"
        "  + google_sql_database_instance.main\n"
    )
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, plan_output, "")
        result = await runner.plan(tmp_path)
        assert "8 to add" in result.raw_output


async def test_apply_returns_outputs(runner: TerraformRunner, tmp_path: Path):
    apply_out = "Apply complete! Resources: 8 added, 0 changed, 0 destroyed."
    output_json = json.dumps({"runtime_url": {"value": "https://runtime.run.app"}})
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [
            (0, apply_out, ""),  # apply
            (0, output_json, ""),  # output
        ]
        result = await runner.apply(tmp_path, auto_approve=True)
        assert result.success is True
        assert result.outputs["runtime_url"] == "https://runtime.run.app"


async def test_apply_failure(runner: TerraformRunner, tmp_path: Path):
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (1, "", "Error: insufficient permissions")
        result = await runner.apply(tmp_path, auto_approve=True)
        assert result.success is False
        assert "insufficient permissions" in result.raw_output


async def test_destroy_calls_terraform(runner: TerraformRunner, tmp_path: Path):
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, "Destroy complete! Resources: 8 destroyed.", "")
        await runner.destroy(tmp_path, auto_approve=True)
        args = mock_run.call_args[0][0]
        assert "destroy" in args


async def test_output_parses_json(runner: TerraformRunner, tmp_path: Path):
    output_json = json.dumps({
        "runtime_url": {"value": "https://runtime.run.app"},
        "db_connection": {"value": "10.0.0.5:5432"},
    })
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, output_json, "")
        outputs = await runner.output(tmp_path)
        assert outputs["runtime_url"] == "https://runtime.run.app"
        assert outputs["db_connection"] == "10.0.0.5:5432"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd astromesh-orbit && uv run pytest tests/test_terraform_runner.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `terraform/runner.py`**

```python
"""TerraformRunner — thin async wrapper around the terraform CLI binary."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from astromesh_orbit.core.provider import ApplyResult, PlanResult


class TerraformNotFoundError(Exception):
    """Raised when terraform binary is not found."""

    def __init__(self) -> None:
        super().__init__(
            "Terraform is not installed or not in PATH.\n"
            "Install it from: https://developer.hashicorp.com/terraform/install"
        )


class TerraformRunner:
    """Async subprocess wrapper for the terraform CLI."""

    async def _run(
        self, args: list[str], cwd: Path | None = None
    ) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode or 0, stdout.decode(), stderr.decode()

    async def check_installed(self) -> str:
        """Check terraform is installed. Returns version string. Raises TerraformNotFoundError."""
        try:
            code, stdout, _ = await self._run(["terraform", "version", "-json"])
        except FileNotFoundError:
            raise TerraformNotFoundError()
        if code != 0:
            raise TerraformNotFoundError()
        try:
            data = json.loads(stdout)
            return data.get("terraform_version", "unknown")
        except json.JSONDecodeError:
            match = re.search(r"Terraform v(\S+)", stdout)
            return match.group(1) if match else "unknown"

    async def init(self, work_dir: Path) -> None:
        code, stdout, stderr = await self._run(
            ["terraform", "init", "-input=false", "-no-color"], cwd=work_dir
        )
        if code != 0:
            raise RuntimeError(f"terraform init failed:\n{stderr or stdout}")

    async def plan(self, work_dir: Path) -> PlanResult:
        code, stdout, stderr = await self._run(
            ["terraform", "plan", "-input=false", "-no-color"], cwd=work_dir
        )
        combined = stdout + stderr
        create = re.findall(r"\+ (\S+)", combined)
        update = re.findall(r"~ (\S+)", combined)
        destroy = re.findall(r"- (\S+)", combined)
        return PlanResult(
            resources_to_create=create,
            resources_to_update=update,
            resources_to_destroy=destroy,
            raw_output=combined,
        )

    async def apply(
        self, work_dir: Path, auto_approve: bool = False
    ) -> ApplyResult:
        args = ["terraform", "apply", "-input=false", "-no-color"]
        if auto_approve:
            args.append("-auto-approve")
        code, stdout, stderr = await self._run(args, cwd=work_dir)
        if code != 0:
            return ApplyResult(success=False, outputs={}, raw_output=stderr or stdout)
        outputs = await self.output(work_dir)
        return ApplyResult(success=True, outputs=outputs, raw_output=stdout)

    async def destroy(
        self, work_dir: Path, auto_approve: bool = False
    ) -> None:
        args = ["terraform", "destroy", "-input=false", "-no-color"]
        if auto_approve:
            args.append("-auto-approve")
        code, stdout, stderr = await self._run(args, cwd=work_dir)
        if code != 0:
            raise RuntimeError(f"terraform destroy failed:\n{stderr or stdout}")

    async def output(self, work_dir: Path) -> dict[str, str]:
        code, stdout, _ = await self._run(
            ["terraform", "output", "-json", "-no-color"], cwd=work_dir
        )
        if code != 0 or not stdout.strip():
            return {}
        data = json.loads(stdout)
        return {k: v["value"] for k, v in data.items() if isinstance(v, dict) and "value" in v}
```

Create `astromesh-orbit/astromesh_orbit/terraform/__init__.py` (empty).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd astromesh-orbit && uv run pytest tests/test_terraform_runner.py -v`
Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add astromesh-orbit/astromesh_orbit/terraform/ astromesh-orbit/tests/test_terraform_runner.py
git commit -m "feat(orbit): add TerraformRunner async subprocess wrapper"
```

---

## Task 5: Wizard defaults and interactive wizard

**Files:**
- Create: `astromesh-orbit/astromesh_orbit/wizard/__init__.py`
- Create: `astromesh-orbit/astromesh_orbit/wizard/defaults.py`
- Create: `astromesh-orbit/astromesh_orbit/wizard/interactive.py`
- Test: `astromesh-orbit/tests/test_wizard.py`

- [ ] **Step 1: Write tests for defaults**

Create `astromesh-orbit/tests/test_wizard.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd astromesh-orbit && uv run pytest tests/test_wizard.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `wizard/defaults.py`**

```python
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
```

- [ ] **Step 4: Implement `wizard/interactive.py`**

```python
"""Interactive wizard for orbit init."""

from __future__ import annotations

from pathlib import Path

import yaml
from rich.console import Console
from rich.prompt import Confirm, Prompt

from astromesh_orbit.wizard.defaults import PRESETS, build_orbit_yaml

console = Console()

GCP_REGIONS = [
    "us-central1",
    "us-east1",
    "us-west1",
    "europe-west1",
    "europe-west4",
    "asia-east1",
    "asia-southeast1",
    "southamerica-east1",
]


def run_wizard(output_path: Path = Path("orbit.yaml")) -> Path:
    """Run the interactive wizard. Returns path to the generated orbit.yaml."""
    console.print("\n  [cyan bold]🛰️  Astromesh Orbit — Cloud Deployment Setup[/]\n")

    # Provider
    provider = Prompt.ask(
        "  Cloud provider",
        choices=["gcp"],
        default="gcp",
    )

    # GCP-specific
    project = Prompt.ask("  GCP Project ID")
    region = Prompt.ask("  Region", choices=GCP_REGIONS, default="us-central1")

    # Name and environment
    name = Prompt.ask("  Deployment name", default="my-astromesh")
    environment = Prompt.ask(
        "  Environment", choices=["dev", "staging", "production"], default="dev"
    )

    # Preset
    console.print()
    for key, p in PRESETS.items():
        cost = p["estimated_cost"]
        ha = "HA" if p["database"]["high_availability"] else "no HA"
        cache = p["cache"]["memory_gb"]
        console.print(f"    [bold]{key}[/] (~${cost}/mo) — {ha}, {cache}GB cache")
    console.print()
    preset = Prompt.ask("  Preset", choices=list(PRESETS.keys()), default="starter")

    data = build_orbit_yaml(
        name=name,
        environment=environment,
        provider=provider,
        project=project,
        region=region,
        preset=preset,
    )

    output_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    console.print(f"\n  [green]✓[/] {output_path} written\n")

    # Append .orbit/ to .gitignore
    gitignore = Path(".gitignore")
    if gitignore.exists():
        content = gitignore.read_text()
        if ".orbit/" not in content:
            with gitignore.open("a") as f:
                f.write("\n# Astromesh Orbit working directory\n.orbit/\n")
            console.print("  [green]✓[/] .orbit/ added to .gitignore\n")
    else:
        gitignore.write_text("# Astromesh Orbit working directory\n.orbit/\n")
        console.print("  [green]✓[/] .gitignore created with .orbit/\n")

    console.print("  Next steps:")
    console.print("    astromeshctl orbit plan     # Preview infrastructure")
    console.print("    astromeshctl orbit apply    # Deploy to GCP\n")

    return output_path
```

Create `astromesh-orbit/astromesh_orbit/wizard/__init__.py` (empty).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd astromesh-orbit && uv run pytest tests/test_wizard.py -v`
Expected: All 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add astromesh-orbit/astromesh_orbit/wizard/ astromesh-orbit/tests/test_wizard.py
git commit -m "feat(orbit): add wizard presets (starter/pro) and interactive init wizard"
```

---

## Task 6: GCP Terraform templates (Jinja2)

**Files:**
- Create: `astromesh-orbit/astromesh_orbit/providers/__init__.py`
- Create: `astromesh-orbit/astromesh_orbit/providers/gcp/__init__.py`
- Create: `astromesh-orbit/astromesh_orbit/providers/gcp/templates/*.tf.j2` (10 files)
- Test: `astromesh-orbit/tests/providers/__init__.py`
- Test: `astromesh-orbit/tests/providers/test_gcp_templates.py`

This is the largest task. The templates are Jinja2 files that generate Terraform HCL. Each template receives the full `OrbitConfig` as context.

- [ ] **Step 1: Write snapshot tests for template rendering**

Create `astromesh-orbit/tests/providers/__init__.py` (empty).

Create `astromesh-orbit/tests/providers/test_gcp_templates.py`:

```python
"""Tests for GCP Terraform template rendering."""

from pathlib import Path
import pytest
from jinja2 import Environment, FileSystemLoader

from astromesh_orbit.config import OrbitConfig


TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "astromesh_orbit" / "providers" / "gcp" / "templates"


@pytest.fixture
def jinja_env():
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )


@pytest.fixture
def config(sample_orbit_yaml: Path) -> OrbitConfig:
    return OrbitConfig.from_yaml(sample_orbit_yaml)


@pytest.fixture
def ctx(config: OrbitConfig) -> dict:
    """Template rendering context."""
    return {
        "config": config,
        "meta": config.metadata,
        "spec": config.spec,
        "provider": config.spec.provider,
        "compute": config.spec.compute,
        "database": config.spec.database,
        "cache": config.spec.cache,
        "secrets": config.spec.secrets,
        "images": config.spec.images,
    }


def test_main_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("main.tf.j2")
    output = tmpl.render(ctx)
    assert 'provider "google"' in output
    assert ctx["provider"].project in output
    assert ctx["provider"].region in output


def test_cloud_run_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("cloud_run.tf.j2")
    output = tmpl.render(ctx)
    assert "google_cloud_run_v2_service" in output
    assert "astromesh-runtime" in output
    assert "astromesh-cloud-api" in output
    assert "astromesh-studio" in output


def test_cloud_sql_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("cloud_sql.tf.j2")
    output = tmpl.render(ctx)
    assert "google_sql_database_instance" in output
    assert ctx["database"].tier in output
    assert ctx["database"].version in output


def test_memorystore_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("memorystore.tf.j2")
    output = tmpl.render(ctx)
    assert "google_redis_instance" in output
    assert str(ctx["cache"].memory_gb) in output


def test_secrets_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("secrets.tf.j2")
    output = tmpl.render(ctx)
    assert "google_secret_manager_secret" in output
    assert "jwt-secret" in output


def test_networking_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("networking.tf.j2")
    output = tmpl.render(ctx)
    assert "google_vpc_access_connector" in output


def test_iam_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("iam.tf.j2")
    output = tmpl.render(ctx)
    assert "google_service_account" in output
    assert "astromesh-orbit" in output
    assert "roles/cloudsql.client" in output


def test_variables_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("variables.tf.j2")
    output = tmpl.render(ctx)
    assert 'variable "project_id"' in output
    assert 'variable "region"' in output


def test_outputs_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("outputs.tf.j2")
    output = tmpl.render(ctx)
    assert "runtime_url" in output
    assert "cloud_api_url" in output
    assert "db_connection_name" in output


def test_backend_tf_renders(jinja_env, ctx):
    tmpl = jinja_env.get_template("backend.tf.j2")
    output = tmpl.render(ctx)
    assert 'backend "gcs"' in output
    assert "astromesh-orbit-state" in output


def test_cloud_run_ha_disabled_uses_min_instances(jinja_env, ctx):
    """Starter preset: studio min_instances=0 should produce scale-to-zero."""
    tmpl = jinja_env.get_template("cloud_run.tf.j2")
    output = tmpl.render(ctx)
    # Studio should have min_instance_count = 0
    assert "min_instance_count" in output


def test_cloud_sql_no_ha(jinja_env, ctx):
    """Starter preset: high_availability is false, no REGIONAL availability_type."""
    tmpl = jinja_env.get_template("cloud_sql.tf.j2")
    output = tmpl.render(ctx)
    assert "ZONAL" in output


def test_secrets_jwt_disabled(jinja_env, ctx):
    """When jwt_secret is False, JWT resources should be omitted."""
    ctx["secrets"] = type("S", (), {"jwt_secret": False, "provider_keys": True})()
    tmpl = jinja_env.get_template("secrets.tf.j2")
    output = tmpl.render(ctx)
    assert "jwt_secret" not in output.lower() or "jwt-secret" not in output


def test_secrets_provider_keys_disabled(jinja_env, ctx):
    """When provider_keys is False, fernet key should be omitted."""
    ctx["secrets"] = type("S", (), {"jwt_secret": True, "provider_keys": False})()
    tmpl = jinja_env.get_template("secrets.tf.j2")
    output = tmpl.render(ctx)
    assert "fernet" not in output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd astromesh-orbit && uv run pytest tests/providers/test_gcp_templates.py -v`
Expected: TemplateNotFound errors — templates don't exist yet.

- [ ] **Step 3: Create all 10 Jinja2 templates**

Create each template in `astromesh-orbit/astromesh_orbit/providers/gcp/templates/`:

**`main.tf.j2`:**
```hcl
terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = "{{ provider.project }}"
  region  = "{{ provider.region }}"
}
```

**`variables.tf.j2`:**
```hcl
variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "{{ provider.project }}"
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "{{ provider.region }}"
}

variable "deployment_name" {
  description = "Deployment name prefix"
  type        = string
  default     = "{{ meta.name }}"
}
```

**`backend.tf.j2`:**
```hcl
terraform {
  backend "gcs" {
    bucket = "{{ provider.project }}-astromesh-orbit-state"
    prefix = "{{ meta.name }}"
  }
}
```

**`iam.tf.j2`:**
```hcl
resource "google_service_account" "orbit" {
  account_id   = "astromesh-orbit"
  display_name = "Astromesh Orbit Service Account"
  project      = var.project_id
}

resource "google_project_iam_member" "cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.orbit.email}"
}

resource "google_project_iam_member" "redis_editor" {
  project = var.project_id
  role    = "roles/redis.editor"
  member  = "serviceAccount:${google_service_account.orbit.email}"
}

resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.orbit.email}"
}

resource "google_project_iam_member" "run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.orbit.email}"
}
```

**`networking.tf.j2`:**
```hcl
resource "google_vpc_access_connector" "orbit" {
  name          = "{{ meta.name }}-vpc"
  project       = var.project_id
  region        = var.region
  ip_cidr_range = "10.8.0.0/28"
  network       = "default"
}
```

**`cloud_sql.tf.j2`:**
```hcl
resource "google_sql_database_instance" "main" {
  name             = "{{ meta.name }}-db"
  database_version = "{{ database.version }}"
  region           = var.region
  project          = var.project_id

  settings {
    tier              = "{{ database.tier }}"
    availability_type = "{{ 'REGIONAL' if database.high_availability else 'ZONAL' }}"
    disk_size         = {{ database.storage_gb }}
    disk_type         = "PD_SSD"

    ip_configuration {
      ipv4_enabled    = false
      private_network = "projects/${var.project_id}/global/networks/default"
    }

    backup_configuration {
      enabled = true
    }
  }

  deletion_protection = false
}

resource "random_password" "db_password" {
  length  = 24
  special = false
}

resource "google_sql_user" "astromesh" {
  name     = "astromesh"
  instance = google_sql_database_instance.main.name
  password = random_password.db_password.result
  project  = var.project_id
}

resource "google_sql_database" "runtime" {
  name     = "astromesh"
  instance = google_sql_database_instance.main.name
  project  = var.project_id
}

resource "google_sql_database" "cloud" {
  name     = "astromesh_cloud"
  instance = google_sql_database_instance.main.name
  project  = var.project_id
}
```

**`memorystore.tf.j2`:**
```hcl
resource "google_redis_instance" "main" {
  name           = "{{ meta.name }}-cache"
  tier           = "{{ cache.tier | upper }}"
  memory_size_gb = {{ cache.memory_gb }}
  region         = var.region
  project        = var.project_id

  authorized_network = "projects/${var.project_id}/global/networks/default"

  redis_version = "REDIS_7_0"
}
```

**`secrets.tf.j2`:**
```hcl
{% if secrets.jwt_secret %}
resource "google_secret_manager_secret" "jwt_secret" {
  secret_id = "{{ meta.name }}-jwt-secret"
  project   = var.project_id

  replication {
    auto {}
  }
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "google_secret_manager_secret_version" "jwt_secret" {
  secret      = google_secret_manager_secret.jwt_secret.id
  secret_data = random_password.jwt_secret.result
}
{% endif %}

{% if secrets.provider_keys %}
resource "google_secret_manager_secret" "fernet_key" {
  secret_id = "{{ meta.name }}-fernet-key"
  project   = var.project_id

  replication {
    auto {}
  }
}
{% endif %}
```

**`cloud_run.tf.j2`:**

Note: Since `compute` is a Pydantic model (not a dict), we use attribute access. The GCPProvider passes a flattened `services` list in the template context to avoid bracket-access issues.

Update `GCPProvider._build_context()` to include:
```python
"services": [
    {"key": "runtime", "name": "astromesh-runtime", "spec": config.spec.compute.runtime, "image": config.spec.images.runtime},
    {"key": "cloud_api", "name": "astromesh-cloud-api", "spec": config.spec.compute.cloud_api, "image": config.spec.images.cloud_api},
    {"key": "studio", "name": "astromesh-studio", "spec": config.spec.compute.studio, "image": config.spec.images.studio},
],
```

```hcl
{% for svc in services %}
resource "google_cloud_run_v2_service" "{{ svc.key }}" {
  name     = "{{ svc.name }}"
  location = var.region
  project  = var.project_id

  template {
    service_account = google_service_account.orbit.email

    scaling {
      min_instance_count = {{ svc.spec.min_instances }}
      max_instance_count = {{ svc.spec.max_instances }}
    }

    vpc_access {
      connector = google_vpc_access_connector.orbit.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = "{{ svc.image }}"

      resources {
        limits = {
          cpu    = "{{ svc.spec.cpu }}"
          memory = "{{ svc.spec.memory }}"
        }
      }
{% if svc.key == "runtime" %}

      env {
        name  = "ASTROMESH_DATABASE_URL"
        value = "postgresql+asyncpg://astromesh:${random_password.db_password.result}@/astromesh?host=/cloudsql/${google_sql_database_instance.main.connection_name}"
      }
      env {
        name  = "ASTROMESH_REDIS_URL"
        value = "redis://${google_redis_instance.main.host}:${google_redis_instance.main.port}"
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
{% elif svc.key == "cloud_api" %}

      env {
        name  = "ASTROMESH_CLOUD_DATABASE_URL"
        value = "postgresql+asyncpg://astromesh:${random_password.db_password.result}@/astromesh_cloud?host=/cloudsql/${google_sql_database_instance.main.connection_name}"
      }
      env {
        name  = "ASTROMESH_CLOUD_RUNTIME_URL"
        value = google_cloud_run_v2_service.runtime.uri
      }
{% if secrets.jwt_secret %}
      env {
        name  = "ASTROMESH_CLOUD_JWT_SECRET"
        value = random_password.jwt_secret.result
      }
{% endif %}

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
{% endif %}
    }
{% if svc.key in ["runtime", "cloud_api"] %}

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }
{% endif %}
  }
}

{% endfor %}
```

**`outputs.tf.j2`:**
```hcl
output "runtime_url" {
  value       = google_cloud_run_v2_service.runtime.uri
  description = "Astromesh runtime URL"
}

output "cloud_api_url" {
  value       = google_cloud_run_v2_service.cloud_api.uri
  description = "Astromesh Cloud API URL"
}

output "studio_url" {
  value       = google_cloud_run_v2_service.studio.uri
  description = "Astromesh Cloud Studio URL"
}

output "db_connection_name" {
  value       = google_sql_database_instance.main.connection_name
  description = "Cloud SQL connection name"
}

output "redis_host" {
  value       = google_redis_instance.main.host
  description = "Memorystore Redis host"
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd astromesh-orbit && uv run pytest tests/providers/test_gcp_templates.py -v`
Expected: All 13 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add astromesh-orbit/astromesh_orbit/providers/ astromesh-orbit/tests/providers/
git commit -m "feat(orbit): add GCP Terraform Jinja2 templates with snapshot tests"
```

---

## Task 7: GCP Provider implementation

**Files:**
- Create: `astromesh-orbit/astromesh_orbit/providers/gcp/provider.py`
- Create: `astromesh-orbit/astromesh_orbit/providers/gcp/validators.py`
- Create: `astromesh-orbit/astromesh_orbit/terraform/backend.py`
- Test: `astromesh-orbit/tests/providers/test_gcp_provider.py`

- [ ] **Step 1: Write tests**

Create `astromesh-orbit/tests/providers/test_gcp_provider.py`:

```python
"""Tests for GCPProvider — template generation and protocol conformance."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from astromesh_orbit.config import OrbitConfig
from astromesh_orbit.core.provider import OrbitProvider
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


async def test_generate_creates_tf_files(provider: GCPProvider, config: OrbitConfig, output_dir: Path):
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


async def test_generate_tf_files_are_valid_hcl(provider: GCPProvider, config: OrbitConfig, output_dir: Path):
    """Generated files should contain valid-looking HCL (basic structural check)."""
    files = await provider.generate(config, output_dir)
    for f in files:
        content = f.read_text()
        assert len(content) > 0, f"{f.name} is empty"
        # Every .tf file should have at least one block
        assert any(
            kw in content for kw in ["resource", "variable", "output", "provider", "terraform"]
        ), f"{f.name} has no HCL blocks"


async def test_generate_includes_project_in_main_tf(provider: GCPProvider, config: OrbitConfig, output_dir: Path):
    await provider.generate(config, output_dir)
    main_tf = (output_dir / "main.tf").read_text()
    assert "test-project-123" in main_tf


async def test_eject_writes_to_output_dir(provider: GCPProvider, config: OrbitConfig, tmp_path: Path):
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
    with patch("astromesh_orbit.providers.gcp.provider.check_gcloud_auth", new_callable=AsyncMock) as auth, \
         patch("astromesh_orbit.providers.gcp.provider.check_project", new_callable=AsyncMock) as proj, \
         patch("astromesh_orbit.providers.gcp.provider.check_apis_enabled", new_callable=AsyncMock) as apis:
        auth.return_value = CheckResult(name="auth", passed=True, message="ok")
        proj.return_value = CheckResult(name="project", passed=True, message="ok")
        apis.return_value = [CheckResult(name="api", passed=True, message="ok")]
        result = await provider.validate(config)
        assert result.ok is True
        auth.assert_called_once()
        proj.assert_called_once_with("test-project-123")


async def test_validate_fails_on_missing_auth(provider: GCPProvider, config: OrbitConfig):
    with patch("astromesh_orbit.providers.gcp.provider.check_gcloud_auth", new_callable=AsyncMock) as auth, \
         patch("astromesh_orbit.providers.gcp.provider.check_project", new_callable=AsyncMock) as proj, \
         patch("astromesh_orbit.providers.gcp.provider.check_apis_enabled", new_callable=AsyncMock) as apis:
        auth.return_value = CheckResult(name="auth", passed=False, message="not authed", remediation="gcloud auth login")
        proj.return_value = CheckResult(name="project", passed=True, message="ok")
        apis.return_value = []
        result = await provider.validate(config)
        assert result.ok is False


async def test_provision_orchestrates_full_flow(provider: GCPProvider, config: OrbitConfig, output_dir: Path):
    """Provision should: validate → ensure bucket → generate → init → apply → write env."""
    with patch.object(provider, "validate", new_callable=AsyncMock) as mock_val, \
         patch.object(provider, "generate", new_callable=AsyncMock) as mock_gen, \
         patch("astromesh_orbit.providers.gcp.provider.ensure_gcs_state_bucket", new_callable=AsyncMock) as mock_bucket, \
         patch.object(provider._tf, "init", new_callable=AsyncMock), \
         patch.object(provider._tf, "apply", new_callable=AsyncMock) as mock_apply:
        mock_val.return_value = ValidationResult(ok=True, checks=[])
        mock_gen.return_value = [output_dir / "main.tf"]
        mock_bucket.return_value = "test-bucket"
        mock_apply.return_value = ApplyResult(
            success=True,
            outputs={"runtime_url": "https://rt.run.app", "cloud_api_url": "https://api.run.app", "studio_url": "https://studio.run.app"},
            raw_output="Apply complete!",
        )
        result = await provider.provision(config, output_dir)
        assert result.endpoints["runtime"] == "https://rt.run.app"
        assert result.env_file.name == "orbit.env"
        mock_val.assert_called_once()
        mock_bucket.assert_called_once()
```

Add these imports at the top of the test file:
```python
from unittest.mock import AsyncMock, patch
from astromesh_orbit.core.provider import CheckResult, ValidationResult, ApplyResult
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd astromesh-orbit && uv run pytest tests/providers/test_gcp_provider.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `providers/gcp/validators.py`**

```python
"""GCP pre-deploy validation helpers."""

from __future__ import annotations

import asyncio
import json

from astromesh_orbit.core.provider import CheckResult

REQUIRED_APIS = [
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "secretmanager.googleapis.com",
    "vpcaccess.googleapis.com",
]


async def _run_gcloud(*args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "gcloud", *args, "--format=json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode(), stderr.decode()


async def check_gcloud_auth() -> CheckResult:
    try:
        code, stdout, _ = await _run_gcloud("auth", "list", "--filter=status:ACTIVE")
        accounts = json.loads(stdout) if stdout.strip() else []
        if code == 0 and accounts:
            return CheckResult(
                name="gcloud_auth",
                passed=True,
                message=f"Authenticated as {accounts[0].get('account', 'unknown')}",
            )
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return CheckResult(
        name="gcloud_auth",
        passed=False,
        message="gcloud CLI not authenticated",
        remediation="gcloud auth login",
    )


async def check_project(project: str) -> CheckResult:
    code, _, _ = await _run_gcloud("projects", "describe", project)
    if code == 0:
        return CheckResult(name="project_exists", passed=True, message=f"Project {project} found")
    return CheckResult(
        name="project_exists",
        passed=False,
        message=f"Project {project} not found or no access",
        remediation=f"Verify the project ID and your permissions: gcloud projects describe {project}",
    )


async def check_apis_enabled(project: str) -> list[CheckResult]:
    code, stdout, _ = await _run_gcloud("services", "list", "--enabled", f"--project={project}")
    enabled = set()
    if code == 0 and stdout.strip():
        try:
            for svc in json.loads(stdout):
                name = svc.get("config", {}).get("name", "")
                enabled.add(name)
        except json.JSONDecodeError:
            pass

    results = []
    for api in REQUIRED_APIS:
        if api in enabled:
            results.append(CheckResult(name=f"api_{api}", passed=True, message=f"{api} enabled"))
        else:
            results.append(CheckResult(
                name=f"api_{api}",
                passed=False,
                message=f"{api} not enabled",
                remediation=f"gcloud services enable {api} --project={project}",
            ))
    return results
```

- [ ] **Step 4: Implement `terraform/backend.py`**

```python
"""State bucket management for Terraform remote backends."""

from __future__ import annotations

import asyncio
import hashlib

from rich.console import Console

console = Console()


async def ensure_gcs_state_bucket(project: str, region: str, name: str) -> str:
    """Create GCS bucket for Terraform state if it doesn't exist. Returns bucket name."""
    bucket_name = f"{project}-astromesh-orbit-state"

    # Check if bucket exists
    proc = await asyncio.create_subprocess_exec(
        "gsutil", "ls", f"gs://{bucket_name}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    if proc.returncode == 0:
        console.print(f"  [green]✓[/] State bucket exists: gs://{bucket_name}")
        return bucket_name

    # Try to create
    proc = await asyncio.create_subprocess_exec(
        "gsutil", "mb", "-p", project, "-l", region, "-b", "on",
        f"gs://{bucket_name}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode == 0:
        # Enable versioning
        await asyncio.create_subprocess_exec(
            "gsutil", "versioning", "set", "on", f"gs://{bucket_name}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        console.print(f"  [green]✓[/] State bucket created: gs://{bucket_name}")
        return bucket_name

    # Naming collision — append hash
    suffix = hashlib.sha256(f"{project}-{name}".encode()).hexdigest()[:6]
    bucket_name = f"{project}-astromesh-orbit-state-{suffix}"
    proc = await asyncio.create_subprocess_exec(
        "gsutil", "mb", "-p", project, "-l", region, "-b", "on",
        f"gs://{bucket_name}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(
            f"Failed to create state bucket gs://{bucket_name}.\n"
            f"Grant roles/storage.admin or create the bucket manually:\n"
            f"  gsutil mb -p {project} -l {region} gs://{bucket_name}"
        )

    console.print(f"  [green]✓[/] State bucket created: gs://{bucket_name}")
    return bucket_name
```

- [ ] **Step 5: Implement `providers/gcp/provider.py`**

```python
"""GCP provider — generates Terraform for Google Cloud."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from astromesh_orbit.config import OrbitConfig
from astromesh_orbit.core.provider import (
    ApplyResult,
    DeploymentStatus,
    ProvisionResult,
    ResourceStatus,
    ValidationResult,
)
from astromesh_orbit.providers.gcp.validators import (
    check_apis_enabled,
    check_gcloud_auth,
    check_project,
)
from astromesh_orbit.terraform.backend import ensure_gcs_state_bucket
from astromesh_orbit.terraform.runner import TerraformRunner

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Templates to render in order
TEMPLATE_FILES = [
    "main.tf.j2",
    "variables.tf.j2",
    "backend.tf.j2",
    "iam.tf.j2",
    "networking.tf.j2",
    "cloud_sql.tf.j2",
    "memorystore.tf.j2",
    "secrets.tf.j2",
    "cloud_run.tf.j2",
    "outputs.tf.j2",
]


class GCPProvider:
    name: str = "gcp"

    def __init__(self) -> None:
        self._jinja = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            keep_trailing_newline=True,
        )
        self._tf = TerraformRunner()

    def _build_context(self, config: OrbitConfig) -> dict:
        return {
            "config": config,
            "meta": config.metadata,
            "spec": config.spec,
            "provider": config.spec.provider,
            "compute": config.spec.compute,
            "database": config.spec.database,
            "cache": config.spec.cache,
            "secrets": config.spec.secrets,
            "images": config.spec.images,
            "services": [
                {"key": "runtime", "name": "astromesh-runtime", "spec": config.spec.compute.runtime, "image": config.spec.images.runtime},
                {"key": "cloud_api", "name": "astromesh-cloud-api", "spec": config.spec.compute.cloud_api, "image": config.spec.images.cloud_api},
                {"key": "studio", "name": "astromesh-studio", "spec": config.spec.compute.studio, "image": config.spec.images.studio},
            ],
        }

    async def validate(self, config: OrbitConfig) -> ValidationResult:
        project = config.spec.provider.project
        checks = [await check_gcloud_auth(), await check_project(project)]
        checks.extend(await check_apis_enabled(project))
        ok = all(c.passed for c in checks)
        return ValidationResult(ok=ok, checks=checks)

    async def generate(self, config: OrbitConfig, output_dir: Path) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        ctx = self._build_context(config)
        generated = []
        for tmpl_name in TEMPLATE_FILES:
            tmpl = self._jinja.get_template(tmpl_name)
            out_name = tmpl_name.replace(".j2", "")
            out_path = output_dir / out_name
            out_path.write_text(tmpl.render(ctx))
            generated.append(out_path)
        return generated

    async def provision(self, config: OrbitConfig, output_dir: Path) -> ProvisionResult:
        # Validate first
        validation = await self.validate(config)
        if not validation.ok:
            failed = [c for c in validation.checks if not c.passed]
            msgs = "\n".join(f"  - {c.message}" + (f" → {c.remediation}" if c.remediation else "") for c in failed)
            raise RuntimeError(f"Validation failed:\n{msgs}")

        # Ensure state bucket
        await ensure_gcs_state_bucket(
            config.spec.provider.project,
            config.spec.provider.region,
            config.metadata.name,
        )

        # Generate and apply
        work_dir = output_dir
        await self.generate(config, work_dir)
        await self._tf.init(work_dir)
        result = await self._tf.apply(work_dir, auto_approve=True)

        if not result.success:
            raise RuntimeError(f"terraform apply failed:\n{result.raw_output}")

        # Write orbit.env
        env_path = output_dir.parent / "orbit.env"
        env_lines = [f"{k.upper()}={v}" for k, v in result.outputs.items()]
        env_path.write_text("\n".join(env_lines) + "\n")

        endpoints = {
            "runtime": result.outputs.get("runtime_url", ""),
            "cloud_api": result.outputs.get("cloud_api_url", ""),
            "studio": result.outputs.get("studio_url", ""),
        }

        return ProvisionResult(apply=result, env_file=env_path, endpoints=endpoints)

    async def status(self, config: OrbitConfig) -> DeploymentStatus:
        outputs = await self._tf.output(Path(".orbit/generated"))
        resources = []
        for key in ["runtime", "cloud_api", "studio"]:
            url_key = f"{key}_url"
            url = outputs.get(url_key)
            resources.append(ResourceStatus(
                name=f"astromesh-{key.replace('_', '-')}",
                resource_type="cloud_run_v2_service",
                status="running" if url else "not_found",
                url=url,
            ))
        return DeploymentStatus(
            resources=resources,
            state_bucket=f"{config.spec.provider.project}-astromesh-orbit-state",
            last_applied=None,
        )

    async def destroy(self, config: OrbitConfig, output_dir: Path) -> None:
        await self._tf.destroy(output_dir, auto_approve=True)

    async def eject(self, config: OrbitConfig, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        ctx = self._build_context(config)
        for tmpl_name in TEMPLATE_FILES:
            tmpl = self._jinja.get_template(tmpl_name)
            out_name = tmpl_name.replace(".j2", "")
            content = tmpl.render(ctx)
            # Add explanatory header comment
            comment = f"# {out_name} — Generated by Astromesh Orbit (ejected)\n# Safe to modify. No Orbit dependency.\n\n"
            (output_dir / out_name).write_text(comment + content)

        # Write terraform.tfvars with resolved values from orbit.yaml
        tfvars_lines = [
            f'project_id      = "{config.spec.provider.project}"',
            f'region          = "{config.spec.provider.region}"',
            f'deployment_name = "{config.metadata.name}"',
        ]
        (output_dir / "terraform.tfvars").write_text("\n".join(tfvars_lines) + "\n")

        return output_dir
```

Update `astromesh-orbit/astromesh_orbit/providers/gcp/__init__.py`:

```python
from astromesh_orbit.providers.gcp.provider import GCPProvider

__all__ = ["GCPProvider"]
```

Create `astromesh-orbit/astromesh_orbit/providers/__init__.py` (empty).

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd astromesh-orbit && uv run pytest tests/providers/test_gcp_provider.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 7: Run all tests**

Run: `cd astromesh-orbit && uv run pytest -v`
Expected: All tests PASS (~34 tests total).

- [ ] **Step 8: Commit**

```bash
git add astromesh-orbit/astromesh_orbit/providers/ astromesh-orbit/astromesh_orbit/terraform/backend.py astromesh-orbit/tests/providers/test_gcp_provider.py
git commit -m "feat(orbit): implement GCPProvider with template generation, validation, and eject"
```

---

## Task 8: CLI plugin discovery in core astromeshctl

**Files:**
- Modify: `cli/main.py`

This is the prerequisite change to the core CLI that enables Orbit (and future plugins) to register commands via entry points.

- [ ] **Step 1: Modify `cli/main.py` to add plugin discovery**

After the existing static imports and `app.add_typer()` calls, add plugin scanning:

```python
# Add at the top of cli/main.py, after existing imports:
import importlib.metadata
import sys

# ... (existing static command registrations stay unchanged) ...

# Plugin discovery — after all static registrations
def _load_plugins(app: typer.Typer) -> None:
    """Discover and register CLI plugins via entry points."""
    try:
        eps = importlib.metadata.entry_points(group="astromeshctl.plugins")
    except TypeError:
        # Python < 3.12 compat
        eps = importlib.metadata.entry_points().get("astromeshctl.plugins", [])
    for ep in eps:
        try:
            register_fn = ep.load()
            register_fn(app)
        except Exception as exc:
            typer.echo(f"Warning: failed to load plugin '{ep.name}': {exc}", err=True)

_load_plugins(app)
```

- [ ] **Step 2: Verify existing commands still work**

Run: `uv run astromeshctl --help`
Expected: All existing commands listed. No errors.

Run: `uv run astromeshctl version`
Expected: Prints version.

- [ ] **Step 3: Commit**

```bash
git add cli/main.py
git commit -m "feat(cli): add plugin discovery via importlib.metadata entry points"
```

---

## Task 9: Orbit CLI commands

**Files:**
- Create: `astromesh-orbit/astromesh_orbit/cli.py`

- [ ] **Step 1: Implement `cli.py`**

```python
"""Orbit CLI — registers as astromeshctl plugin."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from astromesh_orbit.config import OrbitConfig
from astromesh_orbit.providers.gcp.provider import GCPProvider
from astromesh_orbit.terraform.runner import TerraformNotFoundError
from astromesh_orbit.wizard.interactive import run_wizard

console = Console()
orbit_app = typer.Typer(name="orbit", help="Cloud-native deployment for Astromesh.", no_args_is_help=True)

PROVIDERS = {"gcp": GCPProvider}
ORBIT_DIR = Path(".orbit")
GENERATED_DIR = ORBIT_DIR / "generated"


def _load_config(config_path: str) -> OrbitConfig:
    path = Path(config_path)
    if not path.exists():
        console.print(f"[red]Error:[/] {path} not found. Run 'astromeshctl orbit init' first.")
        raise typer.Exit(1)
    return OrbitConfig.from_yaml(path)


def _get_provider(config: OrbitConfig):
    name = config.spec.provider.name
    if name not in PROVIDERS:
        console.print(f"[red]Error:[/] Provider '{name}' not supported. Available: {list(PROVIDERS.keys())}")
        raise typer.Exit(1)
    return PROVIDERS[name]()


@orbit_app.command()
def init(
    provider: str = typer.Option("gcp", help="Cloud provider"),
    preset: Optional[str] = typer.Option(None, help="Preset: starter or pro"),
):
    """Interactive setup — generates orbit.yaml."""
    run_wizard()


@orbit_app.command()
def plan(config: str = typer.Option("orbit.yaml", help="Path to orbit.yaml")):
    """Preview infrastructure changes."""
    async def _plan():
        cfg = _load_config(config)
        prov = _get_provider(cfg)

        console.print("\n  [cyan bold]📋 Orbit Deployment Plan[/]\n")

        # Validate
        console.print("  Validating...", end="")
        validation = await prov.validate(cfg)
        if not validation.ok:
            console.print(" [red]FAILED[/]\n")
            for c in validation.checks:
                icon = "[green]✓[/]" if c.passed else "[red]✗[/]"
                console.print(f"    {icon} {c.message}")
                if c.remediation:
                    console.print(f"      → {c.remediation}")
            raise typer.Exit(1)
        console.print(" [green]OK[/]")

        # Generate and plan
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        await prov.generate(cfg, GENERATED_DIR)
        try:
            from astromesh_orbit.terraform.runner import TerraformRunner
            runner = TerraformRunner()
            await runner.check_installed()
            from astromesh_orbit.terraform.backend import ensure_gcs_state_bucket
            await ensure_gcs_state_bucket(
                cfg.spec.provider.project, cfg.spec.provider.region, cfg.metadata.name
            )
            await runner.init(GENERATED_DIR)
            result = await runner.plan(GENERATED_DIR)
            console.print(f"\n  Resources to create: {len(result.resources_to_create)}")
            console.print(f"  Resources to update: {len(result.resources_to_update)}")
            console.print(f"  Resources to destroy: {len(result.resources_to_destroy)}")
            if result.estimated_monthly_cost:
                console.print(f"  Estimated cost: ~${result.estimated_monthly_cost}/month")
        except TerraformNotFoundError as e:
            console.print(f"\n  [red]{e}[/]")
            raise typer.Exit(1)

    asyncio.run(_plan())


@orbit_app.command()
def apply(
    config: str = typer.Option("orbit.yaml", help="Path to orbit.yaml"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Skip confirmation"),
):
    """Deploy infrastructure to the cloud."""
    async def _apply():
        cfg = _load_config(config)
        prov = _get_provider(cfg)
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)

        console.print("\n  [cyan bold]🛰️  Astromesh Orbit — Deploying[/]\n")

        try:
            result = await prov.provision(cfg, GENERATED_DIR)
        except RuntimeError as e:
            console.print(f"  [red]Error:[/] {e}")
            raise typer.Exit(1)

        console.print("\n  [green bold]✓ Deployment complete![/]\n")

        table = Table(title="Endpoints")
        table.add_column("Service", style="cyan")
        table.add_column("URL", style="green")
        for svc, url in result.endpoints.items():
            if url:
                table.add_row(svc, url)
        console.print(table)
        console.print(f"\n  Environment file: {result.env_file}\n")

    asyncio.run(_apply())


@orbit_app.command()
def status(config: str = typer.Option("orbit.yaml", help="Path to orbit.yaml")):
    """Show deployment status."""
    async def _status():
        cfg = _load_config(config)
        prov = _get_provider(cfg)
        ds = await prov.status(cfg)

        table = Table(title="Deployment Status")
        table.add_column("Resource", style="cyan")
        table.add_column("Type")
        table.add_column("Status")
        table.add_column("URL", style="dim")
        for r in ds.resources:
            color = "green" if r.status == "running" else "red"
            table.add_row(r.name, r.resource_type, f"[{color}]{r.status}[/]", r.url or "—")
        console.print(table)
        console.print(f"\n  State bucket: {ds.state_bucket}")

    asyncio.run(_status())


@orbit_app.command()
def destroy(
    config: str = typer.Option("orbit.yaml", help="Path to orbit.yaml"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Skip confirmation"),
):
    """Destroy all provisioned infrastructure."""
    async def _destroy():
        cfg = _load_config(config)
        prov = _get_provider(cfg)

        if not auto_approve:
            typer.confirm("This will destroy ALL infrastructure. Continue?", abort=True)

        console.print("\n  [yellow]Destroying infrastructure...[/]\n")
        await prov.destroy(cfg, GENERATED_DIR)
        console.print("  [green]✓ All resources destroyed.[/]\n")

    asyncio.run(_destroy())


@orbit_app.command()
def eject(output_dir: str = typer.Option("./orbit-terraform", help="Output directory")):
    """Export standalone Terraform files."""
    async def _eject():
        cfg = _load_config("orbit.yaml")
        prov = _get_provider(cfg)
        result = await prov.eject(cfg, Path(output_dir))
        console.print(f"\n  [green]✓[/] Terraform files exported to {result}/")
        console.print("  These are standalone — no Orbit dependency.\n")
        console.print("  Next steps:")
        console.print(f"    cd {output_dir}")
        console.print("    terraform plan")
        console.print("    terraform apply\n")

    asyncio.run(_eject())


def register(app: typer.Typer) -> None:
    """Plugin entry point — called by astromeshctl plugin discovery."""
    app.add_typer(orbit_app, name="orbit")
```

- [ ] **Step 2: Verify CLI registration works**

Run: `cd astromesh-orbit && uv sync --extra dev --extra gcp && cd .. && uv pip install -e astromesh-orbit`
Then: `uv run astromeshctl orbit --help`
Expected: Shows orbit subcommands (init, plan, apply, status, destroy, eject).

- [ ] **Step 3: Commit**

```bash
git add astromesh-orbit/astromesh_orbit/cli.py
git commit -m "feat(orbit): add CLI commands (init, plan, apply, status, destroy, eject)"
```

---

## Task 10: .gitignore update and roadmap doc

**Files:**
- Modify: `.gitignore`
- Already created: `astromesh-orbit/docs/roadmap.md` (Task 1)

- [ ] **Step 1: Add `.orbit/` to root `.gitignore`**

Append to `.gitignore`:

```
# Astromesh Orbit working directory
.orbit/
```

- [ ] **Step 2: Lint and final test run**

Run: `cd astromesh-orbit && uv run ruff check astromesh_orbit/ tests/`
Fix any issues.

Run: `cd astromesh-orbit && uv run ruff format astromesh_orbit/ tests/`

Run: `cd astromesh-orbit && uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore(orbit): add .orbit/ to gitignore and finalize v0.1.0"
```

---

## Task Summary

| Task | Component | Tests | Dependencies |
|---|---|---|---|
| 1 | Scaffold subproject | — | — |
| 2 | Core data types (Protocol, dataclasses) | 12 | Task 1 |
| 3 | OrbitConfig (Pydantic YAML parser) | 11 | Task 1 |
| 4 | TerraformRunner (subprocess wrapper) | 8 | Task 2 |
| 5 | Wizard (defaults + interactive) | 8 | Task 3 |
| 6 | GCP Terraform templates (Jinja2) | 15 | Task 3 |
| 7 | GCP Provider implementation | 8 | Tasks 4, 6 |
| 8 | CLI plugin discovery (core change) | manual | — |
| 9 | Orbit CLI commands | manual | Tasks 7, 8 |
| 10 | Gitignore + lint + final tests | all | Task 9 |

**Total estimated tests:** ~62 unit/snapshot tests.

**Parallelizable tasks:** Tasks 2+3 can run in parallel. Tasks 4+5+6 can run in parallel (after 2+3). Tasks 8 is independent of all Orbit tasks.
