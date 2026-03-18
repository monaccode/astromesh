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
