"""LaunchdManager — macOS launchd service adapter."""

from __future__ import annotations

import asyncio
import logging
import shutil
import signal
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("astromesh_node.platform.launchd")

PLIST_LABEL = "com.astromesh.daemon"
PLIST_DST = Path("/Library/LaunchDaemons") / f"{PLIST_LABEL}.plist"
PLIST_SRC = Path(__file__).parent.parent.parent.parent / "packaging" / "launchd" / f"{PLIST_LABEL}.plist"


class LaunchdManager:
    """ServiceManager implementation for macOS launchd."""

    def __init__(self) -> None:
        self._reload_handler: Callable[[], Any] | None = None

    async def notify_ready(self) -> None:
        pass  # launchd assumes the process is ready once started

    async def notify_reload(self) -> None:
        pass  # Reload handled via SIGHUP in register_reload_handler

    async def notify_stopping(self) -> None:
        pass

    async def install_service(self, profile: str) -> None:
        if PLIST_SRC.exists():
            shutil.copy2(PLIST_SRC, PLIST_DST)
        proc = await asyncio.create_subprocess_exec(
            "launchctl", "load", "-w", str(PLIST_DST),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        logger.info("Loaded %s", PLIST_LABEL)

    async def uninstall_service(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            "launchctl", "unload", str(PLIST_DST),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if PLIST_DST.exists():
            PLIST_DST.unlink()
        logger.info("Unloaded %s", PLIST_LABEL)

    async def service_status(self) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            "launchctl", "list", PLIST_LABEL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode()
        pid = None
        running = False
        if proc.returncode == 0 and '"PID"' in output:
            running = True
            for line in output.splitlines():
                if '"PID"' in line:
                    pid = int("".join(c for c in line if c.isdigit()))
                    break

        return {
            "running": running,
            "enabled": PLIST_DST.exists(),
            "pid": pid,
            "mode": "launchd",
        }

    def register_reload_handler(self, callback: Callable[[], Any]) -> None:
        self._reload_handler = callback

        def _handle_sighup(signum, frame):
            logger.info("Received SIGHUP, triggering config reload")
            if self._reload_handler:
                self._reload_handler()

        signal.signal(signal.SIGHUP, _handle_sighup)
