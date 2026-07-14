"""Cloud Logging reads for the runtime service (gcloud wrapper — no live calls in tests)."""

from unittest.mock import AsyncMock, patch

import pytest

from astromesh_orbit.providers.gcp.logs import LogsError, build_logs_args, read_logs


def test_build_logs_args_filters_by_service_and_project():
    args = build_logs_args(project="p1", service="astromesh-runtime", limit=25, since="2h")
    assert args[0] == "logging"
    assert args[1] == "read"
    assert 'resource.type="cloud_run_revision"' in args[2]
    assert 'resource.labels.service_name="astromesh-runtime"' in args[2]
    assert "--project=p1" in args
    assert "--limit=25" in args
    assert "--freshness=2h" in args


async def test_read_logs_parses_entries():
    payload = '[{"timestamp": "t0", "severity": "INFO", "textPayload": "hello"}]'
    with patch("astromesh_orbit.providers.gcp.logs.run_gcloud", new_callable=AsyncMock) as gcloud:
        gcloud.return_value = (0, payload, "")
        entries = await read_logs(project="p1", service="astromesh-runtime")
    assert entries == [{"timestamp": "t0", "severity": "INFO", "textPayload": "hello"}]


async def test_read_logs_empty_output_is_empty_list():
    with patch("astromesh_orbit.providers.gcp.logs.run_gcloud", new_callable=AsyncMock) as gcloud:
        gcloud.return_value = (0, "", "")
        assert await read_logs(project="p1", service="astromesh-runtime") == []


async def test_read_logs_raises_on_gcloud_failure():
    with patch("astromesh_orbit.providers.gcp.logs.run_gcloud", new_callable=AsyncMock) as gcloud:
        gcloud.return_value = (1, "", "You do not have permission")
        with pytest.raises(LogsError, match="permission"):
            await read_logs(project="p1", service="astromesh-runtime")
