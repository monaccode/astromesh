"""WindowsServiceManager — Windows Service adapter."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger("astromesh_node.platform.windows")

SERVICE_NAME = "astromeshd"
SERVICE_DISPLAY = "Astromesh Agent Runtime Daemon"


class WindowsServiceManager:
    """ServiceManager implementation for Windows Services."""

    def __init__(self) -> None:
        self._reload_handler: Callable[[], Any] | None = None
        self._service_handle = None

    async def notify_ready(self) -> None:
        pass

    async def notify_reload(self) -> None:
        pass

    async def notify_stopping(self) -> None:
        pass

    async def install_service(self, profile: str) -> None:
        try:
            import win32serviceutil
            import win32service

            win32serviceutil.InstallService(
                None,
                SERVICE_NAME,
                SERVICE_DISPLAY,
                startType=win32service.SERVICE_AUTO_START,
            )
            logger.info("Installed Windows Service: %s", SERVICE_NAME)
        except ImportError:
            proc = await asyncio.create_subprocess_exec(
                "sc", "create", SERVICE_NAME,
                f"binPath={_get_service_binpath()}",
                "start=auto",
                f"DisplayName={SERVICE_DISPLAY}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                logger.info("Installed Windows Service via sc.exe: %s", SERVICE_NAME)
            else:
                raise RuntimeError(f"Failed to install service: {stderr.decode()}")

    async def uninstall_service(self) -> None:
        try:
            import win32serviceutil

            win32serviceutil.RemoveService(SERVICE_NAME)
            logger.info("Removed Windows Service: %s", SERVICE_NAME)
        except ImportError:
            proc = await asyncio.create_subprocess_exec(
                "sc", "delete", SERVICE_NAME,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

    async def service_status(self) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            "sc", "query", SERVICE_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await proc.communicate()
        stdout = stdout_bytes.decode()
        running = "RUNNING" in stdout if proc.returncode == 0 else False
        pid = None
        for line in stdout.splitlines():
            if "PID" in line:
                pid = int("".join(c for c in line if c.isdigit()) or "0") or None
                break

        return {
            "running": running,
            "enabled": proc.returncode == 0,
            "pid": pid,
            "mode": "windows_service",
        }

    def register_reload_handler(self, callback: Callable[[], Any]) -> None:
        self._reload_handler = callback


def _get_service_binpath() -> str:
    """Get the binpath for sc.exe create command."""
    import sys
    from pathlib import Path

    venv = Path(sys.executable).parent
    service_py = venv.parent / "packaging" / "windows" / "astromeshd-service.py"
    return f'"{sys.executable}" "{service_py}"'
