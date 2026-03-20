"""SystemdManager — Linux systemd service adapter."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any, Callable

logger = logging.getLogger("astromesh_node.platform.systemd")

SERVICE_NAME = "astromeshd.service"


class SystemdManager:
    """ServiceManager implementation for Linux systemd."""

    def __init__(self) -> None:
        self._reload_handler: Callable[[], Any] | None = None

    def _get_notifier(self):
        """Return sdnotify notifier, or None if unavailable."""
        try:
            import sdnotify

            return sdnotify.SystemdNotifier()
        except ImportError:
            return None

    async def notify_ready(self) -> None:
        notifier = self._get_notifier()
        if notifier:
            notifier.notify("READY=1")
            logger.info("Notified systemd: READY")

    async def notify_reload(self) -> None:
        notifier = self._get_notifier()
        if notifier:
            notifier.notify("RELOADING=1")

    async def notify_stopping(self) -> None:
        notifier = self._get_notifier()
        if notifier:
            notifier.notify("STOPPING=1")

    async def install_service(self, profile: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "daemon-reload",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "enable", SERVICE_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        logger.info("Enabled %s", SERVICE_NAME)

    async def uninstall_service(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "disable", SERVICE_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        logger.info("Disabled %s", SERVICE_NAME)

    async def service_status(self) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "show", SERVICE_NAME,
            "--property=ActiveState,SubState,MainPID,ActiveEnterTimestamp,UnitFileState",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        props = {}
        for line in stdout.decode().strip().splitlines():
            if "=" in line:
                key, val = line.split("=", 1)
                props[key] = val

        return {
            "running": props.get("ActiveState") == "active",
            "sub_state": props.get("SubState", "unknown"),
            "pid": int(props["MainPID"]) if props.get("MainPID", "0") != "0" else None,
            "enabled": props.get("UnitFileState") == "enabled",
            "since": props.get("ActiveEnterTimestamp"),
            "mode": "systemd",
        }

    def register_reload_handler(self, callback: Callable[[], Any]) -> None:
        self._reload_handler = callback

        def _handle_sighup(signum, frame):
            logger.info("Received SIGHUP, triggering config reload")
            if self._reload_handler:
                self._reload_handler()

        signal.signal(signal.SIGHUP, _handle_sighup)
