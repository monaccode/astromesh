"""ServiceManagerProtocol — abstracts platform init systems."""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable


class UnsupportedPlatformError(Exception):
    """Raised when the current platform is not supported."""


@runtime_checkable
class ServiceManagerProtocol(Protocol):
    """Abstraction of the platform's init system.

    Implementations: SystemdManager (Linux), LaunchdManager (macOS),
    WindowsServiceManager (Windows), ForegroundManager (dev/Docker).
    """

    async def notify_ready(self) -> None:
        """Signal to the init system that the daemon is ready."""
        ...

    async def notify_reload(self) -> None:
        """Signal that a config reload completed."""
        ...

    async def notify_stopping(self) -> None:
        """Signal that the daemon is shutting down."""
        ...

    async def install_service(self, profile: str) -> None:
        """Register astromeshd as a system service."""
        ...

    async def uninstall_service(self) -> None:
        """Unregister the system service."""
        ...

    async def service_status(self) -> dict[str, Any]:
        """Return service status (running, enabled, pid, uptime)."""
        ...

    def register_reload_handler(self, callback: Callable[[], Any]) -> None:
        """Register a handler for config reload signals."""
        ...
