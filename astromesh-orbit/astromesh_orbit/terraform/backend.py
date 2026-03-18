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
        "gsutil",
        "ls",
        f"gs://{bucket_name}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    if proc.returncode == 0:
        console.print(f"  [green]\u2713[/] State bucket exists: gs://{bucket_name}")
        return bucket_name

    # Try to create
    proc = await asyncio.create_subprocess_exec(
        "gsutil",
        "mb",
        "-p",
        project,
        "-l",
        region,
        "-b",
        "on",
        f"gs://{bucket_name}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode == 0:
        # Enable versioning
        await asyncio.create_subprocess_exec(
            "gsutil",
            "versioning",
            "set",
            "on",
            f"gs://{bucket_name}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        console.print(f"  [green]\u2713[/] State bucket created: gs://{bucket_name}")
        return bucket_name

    # Naming collision — append hash
    suffix = hashlib.sha256(f"{project}-{name}".encode()).hexdigest()[:6]
    bucket_name = f"{project}-astromesh-orbit-state-{suffix}"
    proc = await asyncio.create_subprocess_exec(
        "gsutil",
        "mb",
        "-p",
        project,
        "-l",
        region,
        "-b",
        "on",
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

    console.print(f"  [green]\u2713[/] State bucket created: gs://{bucket_name}")
    return bucket_name
