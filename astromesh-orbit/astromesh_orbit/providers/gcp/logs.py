"""Read a Cloud Run service's logs from Cloud Logging via the gcloud CLI."""

from __future__ import annotations

import json

from astromesh_orbit.providers.gcp.gcloud import run_gcloud

_FILTER = 'resource.type="cloud_run_revision" AND resource.labels.service_name="{service}"'


class LogsError(RuntimeError):
    """gcloud could not read the logs (not authenticated, no permission, no such project...)."""


def build_logs_args(project: str, service: str, limit: int, since: str) -> list[str]:
    """The gcloud argv for reading a Cloud Run service's log entries."""
    return [
        "logging",
        "read",
        _FILTER.format(service=service),
        f"--project={project}",
        f"--limit={limit}",
        f"--freshness={since}",
    ]


async def read_logs(project: str, service: str, limit: int = 50, since: str = "1h") -> list[dict]:
    """Newest-first log entries for the service. Raises LogsError if gcloud fails."""
    code, out, err = await run_gcloud(*build_logs_args(project, service, limit, since))
    if code != 0:
        raise LogsError(err.strip() or "gcloud logging read failed")
    return json.loads(out) if out.strip() else []
