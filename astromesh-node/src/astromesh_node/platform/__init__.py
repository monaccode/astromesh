"""Platform abstraction layer for init system integration."""

from astromesh_node.platform.base import ServiceManagerProtocol, UnsupportedPlatformError
from astromesh_node.platform.detect import get_service_manager

__all__ = ["ServiceManagerProtocol", "UnsupportedPlatformError", "get_service_manager"]
