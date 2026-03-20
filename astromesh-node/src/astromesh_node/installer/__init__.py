"""Installer abstraction — platform-specific filesystem and service setup."""

from astromesh_node.installer.base import InstallerProtocol
from astromesh_node.installer.detect import get_installer

__all__ = ["InstallerProtocol", "get_installer"]
