"""State bucket management for Terraform remote backends."""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys

from rich.console import Console

console = Console()

# gsutil is a .cmd on Windows
_GSUTIL = "gsutil.cmd" if sys.platform == "win32" else "gsutil"


async def _run_gsutil(*args: str) -> tuple[int, str, str]:
    """Run gsutil with FileNotFoundError handling."""
    try:
        proc = await asyncio.create_subprocess_exec(
            _GSUTIL,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return 127, "", "gsutil not found in PATH"
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode(), stderr.decode()


def _try_gcs_python(project: str, region: str, bucket_name: str) -> bool | None:
    """Try to create/check bucket via google-cloud-storage. Returns None if lib unavailable."""
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return None
    try:
        from google.cloud import storage  # noqa: lazy import
    except ImportError:
        return None

    try:
        client = storage.Client(project=project)
        bucket = client.bucket(bucket_name)
        if bucket.exists():
            console.print(f"  [green]OK[/] State bucket exists: gs://{bucket_name}")
            return True
        new_bucket = client.create_bucket(bucket_name, location=region)
        new_bucket.versioning_enabled = True
        new_bucket.patch()
        console.print(f"  [green]OK[/] State bucket created: gs://{bucket_name}")
        return True
    except Exception as exc:
        console.print(f"  [yellow]WARN[/] GCS API error: {exc}")
        return False


async def ensure_gcs_state_bucket(project: str, region: str, name: str) -> str:
    """Create GCS bucket for Terraform state if it doesn't exist. Returns bucket name."""
    bucket_name = f"{project}-astromesh-orbit-state"

    # Try Python API first (works with service account, no gsutil needed)
    result = _try_gcs_python(project, region, bucket_name)
    if result is True:
        return bucket_name
    if result is False:
        # API error — try with hash suffix
        suffix = hashlib.sha256(f"{project}-{name}".encode()).hexdigest()[:6]
        alt_name = f"{bucket_name}-{suffix}"
        alt_result = _try_gcs_python(project, region, alt_name)
        if alt_result is True:
            return alt_name
        raise RuntimeError(
            f"Failed to create state bucket.\n"
            f"Grant roles/storage.admin to the service account or create manually:\n"
            f"  gsutil mb -p {project} -l {region} gs://{bucket_name}"
        )

    # Fallback to gsutil CLI
    code, _, _ = await _run_gsutil("ls", f"gs://{bucket_name}")
    if code == 0:
        console.print(f"  [green]OK[/] State bucket exists: gs://{bucket_name}")
        return bucket_name

    if code == 127:
        raise RuntimeError(
            "Neither google-cloud-storage Python library nor gsutil CLI found.\n"
            "Install the Google Cloud SDK: https://cloud.google.com/sdk/docs/install"
        )

    # Try to create via gsutil
    code, _, stderr = await _run_gsutil(
        "mb", "-p", project, "-l", region, "-b", "on", f"gs://{bucket_name}",
    )
    if code == 0:
        await _run_gsutil("versioning", "set", "on", f"gs://{bucket_name}")
        console.print(f"  [green]OK[/] State bucket created: gs://{bucket_name}")
        return bucket_name

    # Naming collision — try with hash suffix
    suffix = hashlib.sha256(f"{project}-{name}".encode()).hexdigest()[:6]
    bucket_name = f"{project}-astromesh-orbit-state-{suffix}"
    code, _, stderr = await _run_gsutil(
        "mb", "-p", project, "-l", region, "-b", "on", f"gs://{bucket_name}",
    )
    if code != 0:
        raise RuntimeError(
            f"Failed to create state bucket gs://{bucket_name}.\n"
            f"Grant roles/storage.admin or create the bucket manually:\n"
            f"  gsutil mb -p {project} -l {region} gs://{bucket_name}"
        )

    console.print(f"  [green]OK[/] State bucket created: gs://{bucket_name}")
    return bucket_name
