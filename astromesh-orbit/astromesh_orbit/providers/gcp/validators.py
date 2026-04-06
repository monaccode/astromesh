"""GCP pre-deploy validation helpers.

Supports two authentication methods:
  1. gcloud CLI — used when GOOGLE_APPLICATION_CREDENTIALS is not set
  2. Service Account key — used when GOOGLE_APPLICATION_CREDENTIALS points to a JSON key file
"""

from __future__ import annotations

import asyncio
import json
import os
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


def _has_service_account_key() -> str | None:
    """Return the path if GOOGLE_APPLICATION_CREDENTIALS is set and the file exists."""
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if path and os.path.isfile(path):
        return path
    return None


# ---------------------------------------------------------------------------
# gcloud CLI helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Service-account (google-auth library) helpers
# ---------------------------------------------------------------------------

def _load_sa_credentials():
    """Load default credentials from GOOGLE_APPLICATION_CREDENTIALS."""
    from google.auth import default  # noqa: lazy import – optional dep
    from google.auth.transport.requests import Request

    creds, project = default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    creds.refresh(Request())
    return creds, project


def _sa_check_auth() -> CheckResult:
    """Validate service-account credentials can be loaded."""
    key_path = _has_service_account_key()
    try:
        creds, _ = _load_sa_credentials()
        email = getattr(creds, "service_account_email", None) or "service-account"
        return CheckResult(
            name="gcloud_auth",
            passed=True,
            message=f"Authenticated via service account: {email}",
        )
    except Exception as exc:
        return CheckResult(
            name="gcloud_auth",
            passed=False,
            message=f"Service account auth failed: {exc}",
            remediation=f"Check GOOGLE_APPLICATION_CREDENTIALS={key_path}",
        )


def _sa_check_project(project: str) -> CheckResult:
    """Validate project exists using google-cloud-resource-manager."""
    try:
        from google.cloud.resourcemanager_v3 import ProjectsClient

        client = ProjectsClient()
        p = client.get_project(name=f"projects/{project}")
        return CheckResult(
            name="project_exists",
            passed=True,
            message=f"Project {p.project_id} found",
        )
    except Exception as exc:
        return CheckResult(
            name="project_exists",
            passed=False,
            message=f"Project {project} not found or no access: {exc}",
            remediation=f"Verify the project ID and service account permissions",
        )


def _sa_check_apis_enabled(project: str) -> list[CheckResult]:
    """Check enabled APIs using the Service Usage REST API via google-auth."""
    try:
        from google.auth.transport.requests import AuthorizedSession

        creds, _ = _load_sa_credentials()
        session = AuthorizedSession(creds)
        url = (
            f"https://serviceusage.googleapis.com/v1/projects/{project}"
            f"/services?filter=state:ENABLED&fields=services/config/name"
        )
        resp = session.get(url)
        resp.raise_for_status()
        data = resp.json()
        enabled = {svc.get("config", {}).get("name", "") for svc in data.get("services", [])}
    except Exception:
        # If we can't query Service Usage, mark all as unknown/failed
        return [
            CheckResult(
                name=f"api_{api}",
                passed=False,
                message=f"{api} — unable to verify (Service Usage API may not be enabled)",
                remediation=f"gcloud services enable serviceusage.googleapis.com --project={project}",
            )
            for api in REQUIRED_APIS
        ]

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


# ---------------------------------------------------------------------------
# Public API — auto-selects auth method
# ---------------------------------------------------------------------------

async def check_gcloud_auth() -> CheckResult:
    if _has_service_account_key():
        return _sa_check_auth()

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
        message="gcloud CLI not authenticated and no service account key found",
        remediation="gcloud auth login  OR  set GOOGLE_APPLICATION_CREDENTIALS",
    )


async def check_project(project: str) -> CheckResult:
    if _has_service_account_key():
        return _sa_check_project(project)

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
    if _has_service_account_key():
        return _sa_check_apis_enabled(project)

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
