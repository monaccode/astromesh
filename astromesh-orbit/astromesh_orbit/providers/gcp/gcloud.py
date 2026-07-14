"""Shared gcloud CLI helper.

Used by the pre-deploy validators and by log reading, so it lives here rather than as a
private in either. Always requests JSON output.
"""

from __future__ import annotations

import asyncio
import sys

# Windows needs gcloud.cmd; create_subprocess_exec can't resolve .cmd from PATH
GCLOUD = "gcloud.cmd" if sys.platform == "win32" else "gcloud"


async def run_gcloud(*args: str) -> tuple[int, str, str]:
    """Run `gcloud <args> --format=json`. Returns (returncode, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            GCLOUD,
            *args,
            "--format=json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return 127, "", "gcloud CLI not found in PATH"
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode(), stderr.decode()
