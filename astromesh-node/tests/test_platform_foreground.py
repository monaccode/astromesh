"""Tests for ForegroundManager (no-op adapter)."""

import pytest

from astromesh_node.platform.base import ServiceManagerProtocol
from astromesh_node.platform.foreground import ForegroundManager


@pytest.fixture
def manager():
    return ForegroundManager()


def test_implements_protocol(manager):
    assert isinstance(manager, ServiceManagerProtocol)


async def test_notify_ready_is_noop(manager):
    await manager.notify_ready()  # Should not raise


async def test_notify_reload_is_noop(manager):
    await manager.notify_reload()


async def test_notify_stopping_is_noop(manager):
    await manager.notify_stopping()


async def test_service_status_returns_foreground(manager):
    status = await manager.service_status()
    assert status["running"] is True
    assert status["mode"] == "foreground"


def test_register_reload_handler_stores_callback(manager):
    called = []
    manager.register_reload_handler(lambda: called.append(True))


async def test_install_service_raises_in_foreground(manager):
    with pytest.raises(RuntimeError, match="foreground"):
        await manager.install_service("full")


async def test_uninstall_service_raises_in_foreground(manager):
    with pytest.raises(RuntimeError, match="foreground"):
        await manager.uninstall_service()
