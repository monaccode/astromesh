"""WindowsInstaller — Windows-specific paths and setup."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("astromesh_node.installer.windows")


class WindowsInstaller:
    """Installer for Windows."""

    def _program_data(self) -> Path:
        return Path(os.environ.get("ProgramData", "C:\\ProgramData"))

    def _program_files(self) -> Path:
        return Path(os.environ.get("ProgramFiles", "C:\\Program Files"))

    def config_dir(self) -> Path:
        return self._program_data() / "Astromesh" / "config"

    def data_dir(self) -> Path:
        return self._program_data() / "Astromesh" / "data"

    def log_dir(self) -> Path:
        return self._program_data() / "Astromesh" / "logs"

    def bin_dir(self) -> Path:
        return self._program_files() / "Astromesh" / "venv"

    async def install(self, profile: str, dry_run: bool = False) -> None:
        dirs = [
            self.config_dir(),
            self.data_dir() / "models",
            self.data_dir() / "memory",
            self.data_dir() / "data",
            self.log_dir(),
        ]
        for d in dirs:
            if dry_run:
                logger.info("[dry-run] mkdir %s", d)
            else:
                d.mkdir(parents=True, exist_ok=True)
                logger.info("Created %s", d)

    async def uninstall(self, keep_data: bool = True) -> None:
        import shutil

        if not keep_data:
            for d in [self.data_dir(), self.log_dir()]:
                if d.exists():
                    shutil.rmtree(d)
                    logger.info("Removed %s", d)

    async def verify(self) -> list[str]:
        problems = []
        for d in [self.config_dir(), self.data_dir(), self.log_dir()]:
            if not d.exists():
                problems.append(f"Directory missing: {d}")
        runtime_yaml = self.config_dir() / "runtime.yaml"
        if not runtime_yaml.exists():
            problems.append("Config missing: runtime.yaml (run 'astromeshctl init')")
        return problems
