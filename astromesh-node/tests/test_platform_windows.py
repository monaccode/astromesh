"""Tests for WindowsServiceManager (Windows Service adapter)."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from astromesh_node.platform.base import ServiceManagerProtocol
from astromesh_node.platform.windows import WindowsServiceManager


@pytest.fixture
def manager():
    return WindowsServiceManager()


def test_implements_protocol(manager):
    assert isinstance(manager, ServiceManagerProtocol)


async def test_notify_ready_is_noop_without_win32(manager):
    """notify_ready gracefully degrades when not running as Windows Service."""
    with patch.object(manager, "_service_handle", None):
        await manager.notify_ready()  # Should not raise


async def test_notify_stopping_is_noop_without_win32(manager):
    with patch.object(manager, "_service_handle", None):
        await manager.notify_stopping()


async def test_service_status_returns_dict(manager):
    with patch("astromesh_node.platform.windows.asyncio") as mock_asyncio:
        proc = AsyncMock()
        proc.communicate.return_value = (
            b"STATE              : 4  RUNNING\nPID                : 5678\n", b""
        )
        proc.returncode = 0
        mock_asyncio.create_subprocess_exec = AsyncMock(return_value=proc)
        mock_asyncio.subprocess = MagicMock()
        mock_asyncio.subprocess.PIPE = -1
        status = await manager.service_status()
        assert status["mode"] == "windows_service"
        assert status["running"] is True


def test_register_reload_handler_stores_callback(manager):
    callback = MagicMock()
    manager.register_reload_handler(callback)
    assert manager._reload_handler == callback
