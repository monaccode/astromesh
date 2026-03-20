"""Auto-detection of the platform's service manager."""

from __future__ import annotations

import sys

from astromesh_node.platform.base import ServiceManagerProtocol, UnsupportedPlatformError
from astromesh_node.platform.foreground import ForegroundManager


def get_service_manager(foreground: bool = False) -> ServiceManagerProtocol:
    """Return the appropriate ServiceManager for the current platform."""
    if foreground:
        return ForegroundManager()

    if sys.platform == "linux":
        from astromesh_node.platform.systemd import SystemdManager

        return SystemdManager()
    elif sys.platform == "darwin":
        from astromesh_node.platform.launchd import LaunchdManager

        return LaunchdManager()
    elif sys.platform == "win32":
        from astromesh_node.platform.windows import WindowsServiceManager

        return WindowsServiceManager()
    else:
        raise UnsupportedPlatformError(f"Platform {sys.platform} is not supported")
