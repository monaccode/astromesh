"""MacOSInstaller — macOS-specific paths and setup."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("astromesh_node.installer.macos")


class MacOSInstaller:
    """Installer for macOS."""

    def config_dir(self) -> Path:
        return Path("/Library/Application Support/Astromesh/config")

    def data_dir(self) -> Path:
        return Path("/Library/Application Support/Astromesh/data")

    def log_dir(self) -> Path:
        return Path("/Library/Logs/Astromesh")

    def bin_dir(self) -> Path:
        return Path("/usr/local/opt/astromesh/venv")

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
