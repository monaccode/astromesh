"""TerraformRunner — thin async wrapper around the tofu/terraform CLI binary."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from pathlib import Path

from astromesh_orbit.core.provider import ApplyResult, PlanResult


def _resolve_binary() -> str:
    """Resolve the IaC binary: TOFU_PATH env > tofu in PATH > terraform in PATH > 'tofu'."""
    tofu_path = os.environ.get("TOFU_PATH")
    if tofu_path and os.path.isfile(tofu_path):
        return tofu_path
    found = shutil.which("tofu") or shutil.which("terraform")
    if found:
        return found
    return "tofu"


class TerraformNotFoundError(Exception):
    """Raised when neither tofu nor terraform binary is found."""

    def __init__(self) -> None:
        super().__init__(
            "OpenTofu/Terraform is not installed or not in PATH.\n"
            "Install OpenTofu from: https://opentofu.org/docs/intro/install/"
        )


class TerraformRunner:
    """Async subprocess wrapper for the tofu/terraform CLI."""

    def __init__(self) -> None:
        self._bin = _resolve_binary()

    async def _run(self, args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode or 0, stdout.decode(), stderr.decode()

    async def check_installed(self) -> str:
        """Check tofu/terraform is installed. Returns version string."""
        try:
            code, stdout, _ = await self._run([self._bin, "version", "-json"])
        except FileNotFoundError:
            raise TerraformNotFoundError()
        if code != 0:
            raise TerraformNotFoundError()
        try:
            data = json.loads(stdout)
            return data.get("terraform_version", data.get("tofu_version", "unknown"))
        except json.JSONDecodeError:
            match = re.search(r"(?:Terraform|OpenTofu) v(\S+)", stdout)
            return match.group(1) if match else "unknown"

    async def init(self, work_dir: Path) -> None:
        code, stdout, stderr = await self._run(
            [self._bin, "init", "-input=false", "-no-color"], cwd=work_dir
        )
        if code != 0:
            raise RuntimeError(f"init failed:\n{stderr or stdout}")

    async def plan(self, work_dir: Path) -> PlanResult:
        code, stdout, stderr = await self._run(
            [self._bin, "plan", "-input=false", "-no-color"], cwd=work_dir
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

    async def apply(self, work_dir: Path, auto_approve: bool = False) -> ApplyResult:
        args = [self._bin, "apply", "-input=false", "-no-color"]
        if auto_approve:
            args.append("-auto-approve")
        code, stdout, stderr = await self._run(args, cwd=work_dir)
        if code != 0:
            return ApplyResult(success=False, outputs={}, raw_output=stderr or stdout)
        outputs = await self.output(work_dir)
        return ApplyResult(success=True, outputs=outputs, raw_output=stdout)

    async def destroy(self, work_dir: Path, auto_approve: bool = False) -> None:
        args = [self._bin, "destroy", "-input=false", "-no-color"]
        if auto_approve:
            args.append("-auto-approve")
        code, stdout, stderr = await self._run(args, cwd=work_dir)
        if code != 0:
            raise RuntimeError(f"destroy failed:\n{stderr or stdout}")

    async def output(self, work_dir: Path) -> dict[str, str]:
        code, stdout, _ = await self._run(
            [self._bin, "output", "-json", "-no-color"], cwd=work_dir
        )
        if code != 0 or not stdout.strip():
            return {}
        data = json.loads(stdout)
        return {k: v["value"] for k, v in data.items() if isinstance(v, dict) and "value" in v}
