"""GCP pre-deploy validation helpers."""

from __future__ import annotations

import asyncio
import json
import sys

from astromesh_orbit.core.provider import CheckResult

REQUIRED_APIS = [
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "secretmanager.googleapis.com",
    "vpcaccess.googleapis.com",
]

# Windows needs gcloud.cmd; create_subprocess_exec can't resolve .cmd from PATH
_GCLOUD = "gcloud.cmd" if sys.platform == "win32" else "gcloud"


async def _run_gcloud(*args: str) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            _GCLOUD,
            *args,
            "--format=json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return 127, "", "gcloud CLI not found in PATH"
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
            results.append(
                CheckResult(
                    name=f"api_{api}",
                    passed=False,
                    message=f"{api} not enabled",
                    remediation=f"gcloud services enable {api} --project={project}",
                )
            )
    return results
