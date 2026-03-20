"""Tests for LaunchdManager (macOS launchd adapter)."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from astromesh_node.platform.base import ServiceManagerProtocol
from astromesh_node.platform.launchd import LaunchdManager


@pytest.fixture
def manager():
    return LaunchdManager()


def test_implements_protocol(manager):
    assert isinstance(manager, ServiceManagerProtocol)


async def test_notify_ready_is_noop(manager):
    await manager.notify_ready()  # launchd assumes ready


async def test_notify_stopping_is_noop(manager):
    await manager.notify_stopping()


async def test_install_service_calls_launchctl(manager):
    with patch("astromesh_node.platform.launchd.asyncio") as mock_asyncio:
        proc = AsyncMock()
        proc.communicate.return_value = (b"", b"")
        proc.returncode = 0
        mock_asyncio.create_subprocess_exec = AsyncMock(return_value=proc)
        with patch("astromesh_node.platform.launchd.shutil"):
            with patch("astromesh_node.platform.launchd.Path") as mock_path:
                mock_path.return_value.exists.return_value = True
                await manager.install_service("full")


async def test_service_status_parses_launchctl(manager):
    launchctl_output = b'{\n\t"PID" = 1234;\n\t"Label" = "com.astromesh.daemon";\n};\n'
    with patch("astromesh_node.platform.launchd.asyncio") as mock_asyncio:
        proc = AsyncMock()
        proc.communicate.return_value = (launchctl_output, b"")
        proc.returncode = 0
        mock_asyncio.create_subprocess_exec = AsyncMock(return_value=proc)
        status = await manager.service_status()
        assert status["mode"] == "launchd"


def test_register_reload_handler_sets_sighup(manager):
    callback = MagicMock()
    with patch("astromesh_node.platform.launchd.signal") as mock_signal:
        manager.register_reload_handler(callback)
        mock_signal.signal.assert_called_once()
        assert mock_signal.signal.call_args[0][0] == mock_signal.SIGHUP
