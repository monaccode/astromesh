"""SystemdManager — Linux systemd service adapter."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from typing import Any, Callable

logger = logging.getLogger("astromesh_node.platform.systemd")

SERVICE_NAME = "astromeshd.service"


class SystemdManager:
    """ServiceManager implementation for Linux systemd."""

    def __init__(self) -> None:
        self._reload_handler: Callable[[], Any] | None = None
        self._watchdog_task: asyncio.Task | None = None

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
            self._start_watchdog(notifier)

    def _start_watchdog(self, notifier) -> None:
        """Ping WATCHDOG=1 at half of WatchdogSec, as sd_watchdog_enabled(3) says.

        Without it systemd kills the unit every WatchdogSec. The ping runs on the
        event loop on purpose: a loop that hangs stops pinging, and systemd restarts it.
        """
        if self._watchdog_task and not self._watchdog_task.done():
            return  # READY=1 again after a reload: the pinger is already running
        usec = os.environ.get("WATCHDOG_USEC")
        pid = os.environ.get("WATCHDOG_PID")
        if not usec or (pid and pid != str(os.getpid())):
            return
        interval = int(usec) / 1_000_000 / 2

        async def _ping() -> None:
            while True:
                notifier.notify("WATCHDOG=1")
                await asyncio.sleep(interval)

        self._watchdog_task = asyncio.create_task(_ping())
        logger.info("systemd watchdog: ping every %.1fs", interval)

    async def notify_reload(self) -> None:
        notifier = self._get_notifier()
        if notifier:
            # MONOTONIC_USEC: systemd ≥ 253 lo exige para asociar el RELOADING al reload.
            notifier.notify(f"RELOADING=1\nMONOTONIC_USEC={time.monotonic_ns() // 1000}")

    async def notify_stopping(self) -> None:
        if self._watchdog_task:
            self._watchdog_task.cancel()
            self._watchdog_task = None
        notifier = self._get_notifier()
        if notifier:
            notifier.notify("STOPPING=1")

    async def install_service(self, profile: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "daemon-reload",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "enable",
            SERVICE_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        logger.info("Enabled %s", SERVICE_NAME)

    async def uninstall_service(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "disable",
            SERVICE_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        logger.info("Disabled %s", SERVICE_NAME)

    async def service_status(self) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "show",
            SERVICE_NAME,
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
