"""ForegroundManager — no-op ServiceManager for dev/Docker/foreground mode."""

from __future__ import annotations

import os
from typing import Any, Callable


class ForegroundManager:
    """No-op service manager for non-daemon contexts."""

    def __init__(self) -> None:
        self._reload_handler: Callable[[], Any] | None = None

    async def notify_ready(self) -> None:
        pass

    async def notify_reload(self) -> None:
        pass

    async def notify_stopping(self) -> None:
        pass

    async def install_service(self, profile: str) -> None:
        raise RuntimeError("Cannot install service in foreground mode")

    async def uninstall_service(self) -> None:
        raise RuntimeError("Cannot uninstall service in foreground mode")

    async def service_status(self) -> dict[str, Any]:
        return {
            "running": True,
            "enabled": False,
            "pid": os.getpid(),
            "mode": "foreground",
        }

    def register_reload_handler(self, callback: Callable[[], Any]) -> None:
        self._reload_handler = callback
