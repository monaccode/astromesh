"""SIGHUP → reload_agents: recarga los agentes sin reiniciar astromeshd."""

import logging
from unittest.mock import AsyncMock, MagicMock

from astromesh_node.daemon.core import reload_agents


def _service_mgr():
    mgr = MagicMock()
    mgr.notify_reload = AsyncMock()
    mgr.notify_ready = AsyncMock()
    return mgr


async def test_reload_brackets_with_reloading_and_ready_and_updates_mesh():
    runtime = MagicMock()
    runtime.reload = AsyncMock(
        return_value={"added": ["tres"], "updated": [], "removed": [], "failed": {}}
    )
    runtime.list_agents.return_value = [{"name": "uno"}, {"name": "tres"}]
    mgr, mesh = _service_mgr(), MagicMock()
    calls = []
    mgr.notify_reload.side_effect = lambda: calls.append("reloading")
    runtime.reload.side_effect = lambda: calls.append("reload") or runtime.reload.return_value
    mgr.notify_ready.side_effect = lambda: calls.append("ready")

    await reload_agents(runtime, mgr, mesh)

    assert calls == ["reloading", "reload", "ready"]
    mesh.update_agents.assert_called_once_with(["uno", "tres"])


async def test_a_failed_reload_keeps_the_daemon_up(caplog):
    runtime = MagicMock()
    runtime.reload = AsyncMock(side_effect=ValueError("Circular agent reference detected: a -> b"))
    mgr = _service_mgr()

    with caplog.at_level(logging.ERROR):
        await reload_agents(runtime, mgr, None)  # must not raise

    mgr.notify_ready.assert_awaited_once()
    assert "Circular" in caplog.text


async def test_runtime_yaml_change_is_flagged(tmp_path, caplog):
    runtime = MagicMock()
    runtime.reload = AsyncMock(
        return_value={"added": [], "updated": [], "removed": [], "failed": {}}
    )
    runtime_yaml = tmp_path / "runtime.yaml"
    runtime_yaml.write_text("spec: {}")
    before = runtime_yaml.stat().st_mtime_ns
    runtime_yaml.write_text("spec: {api: {port: 9000}}")
    import os

    os.utime(runtime_yaml, ns=(before + 10**9, before + 10**9))

    with caplog.at_level(logging.WARNING):
        await reload_agents(
            runtime, _service_mgr(), None, runtime_yaml=runtime_yaml, runtime_yaml_mtime=before
        )

    assert "runtime.yaml" in caplog.text and "reinici" in caplog.text
