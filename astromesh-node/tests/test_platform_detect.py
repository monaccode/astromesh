"""Tests for platform auto-detection."""

from unittest.mock import patch

from astromesh_node.platform.base import UnsupportedPlatformError
from astromesh_node.platform.detect import get_service_manager
from astromesh_node.platform.foreground import ForegroundManager

import pytest


def test_foreground_flag_returns_foreground_manager():
    mgr = get_service_manager(foreground=True)
    assert isinstance(mgr, ForegroundManager)


def test_unsupported_platform_raises():
    with patch("astromesh_node.platform.detect.sys") as mock_sys:
        mock_sys.platform = "freebsd"
        with pytest.raises(UnsupportedPlatformError, match="freebsd"):
            get_service_manager(foreground=False)


def test_linux_returns_systemd_manager():
    with patch("astromesh_node.platform.detect.sys") as mock_sys:
        mock_sys.platform = "linux"
        mgr = get_service_manager(foreground=False)
        assert type(mgr).__name__ == "SystemdManager"


def test_darwin_returns_launchd_manager():
    with patch("astromesh_node.platform.detect.sys") as mock_sys:
        mock_sys.platform = "darwin"
        mgr = get_service_manager(foreground=False)
        assert type(mgr).__name__ == "LaunchdManager"


def test_win32_returns_windows_manager():
    with patch("astromesh_node.platform.detect.sys") as mock_sys:
        mock_sys.platform = "win32"
        mgr = get_service_manager(foreground=False)
        assert type(mgr).__name__ == "WindowsServiceManager"
