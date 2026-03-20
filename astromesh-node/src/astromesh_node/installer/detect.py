"""Auto-detection of the platform's installer."""

from __future__ import annotations

import sys

from astromesh_node.installer.base import InstallerProtocol


def get_installer() -> InstallerProtocol:
    """Return the appropriate Installer for the current platform."""
    if sys.platform == "linux":
        from astromesh_node.installer.linux import LinuxInstaller

        return LinuxInstaller()
    elif sys.platform == "darwin":
        from astromesh_node.installer.macos import MacOSInstaller

        return MacOSInstaller()
    elif sys.platform == "win32":
        from astromesh_node.installer.windows import WindowsInstaller

        return WindowsInstaller()
    else:
        from astromesh_node.platform.base import UnsupportedPlatformError

        raise UnsupportedPlatformError(f"Platform {sys.platform} is not supported")
