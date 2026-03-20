"""Tests for SystemdManager (Linux systemd adapter)."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from astromesh_node.platform.base import ServiceManagerProtocol
from astromesh_node.platform.systemd import SystemdManager


@pytest.fixture
def manager():
    return SystemdManager()


def test_implements_protocol(manager):
    assert isinstance(manager, ServiceManagerProtocol)


async def test_notify_ready_calls_sdnotify(manager):
    mock_notifier = MagicMock()
    with patch.object(manager, "_get_notifier", return_value=mock_notifier):
        await manager.notify_ready()
        mock_notifier.notify.assert_called_once_with("READY=1")


async def test_notify_ready_noop_without_sdnotify(manager):
    with patch.object(manager, "_get_notifier", return_value=None):
        await manager.notify_ready()  # Should not raise


async def test_notify_stopping_calls_sdnotify(manager):
    mock_notifier = MagicMock()
    with patch.object(manager, "_get_notifier", return_value=mock_notifier):
        await manager.notify_stopping()
        mock_notifier.notify.assert_called_once_with("STOPPING=1")


async def test_notify_reload_calls_sdnotify(manager):
    mock_notifier = MagicMock()
    with patch.object(manager, "_get_notifier", return_value=mock_notifier):
        await manager.notify_reload()
        mock_notifier.notify.assert_called_once_with("RELOADING=1")


async def test_service_status_parses_systemctl(manager):
    systemctl_output = (
        "ActiveState=active\nSubState=running\nMainPID=1234\n"
        "ActiveEnterTimestamp=Thu 2026-03-20 10:00:00 UTC\n"
        "UnitFileState=enabled\n"
    )
    with patch("astromesh_node.platform.systemd.asyncio") as mock_asyncio:
        proc = AsyncMock()
        proc.communicate.return_value = (systemctl_output.encode(), b"")
        proc.returncode = 0
        mock_asyncio.create_subprocess_exec = AsyncMock(return_value=proc)
        status = await manager.service_status()
        assert status["running"] is True
        assert status["pid"] == 1234
        assert status["enabled"] is True


def test_register_reload_handler_sets_sighup(manager):
    callback = MagicMock()
    with patch("astromesh_node.platform.systemd.signal") as mock_signal:
        manager.register_reload_handler(callback)
        mock_signal.signal.assert_called_once()
        args = mock_signal.signal.call_args
        assert args[0][0] == mock_signal.SIGHUP
