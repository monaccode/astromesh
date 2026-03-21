"""Centralized logging for Astromesh API and runtime.

Environment variables
---------------------
ASTROMESH_LOG_LEVEL
    Root level for the ``astromesh`` logger tree. Default: ``DEBUG`` (detailed).
    Values: DEBUG, INFO, WARNING, ERROR, CRITICAL (case-insensitive).

ASTROMESH_LOG_FORMAT
    ``logging`` format string. Default includes time, level, logger name, message.

ASTROMESH_LOG_DATEFMT
    ``strftime`` format for ``%(asctime)s``. Default: ``%Y-%m-%dT%H:%M:%S``.

ASTROMESH_LOG_THIRDPARTY_LEVEL
    Level cap for noisy libraries (httpx, httpcore, etc.). Default: ``WARNING``.
    Set to ``DEBUG`` or ``INFO`` to see their logs too.

ASTROMESH_LOG_CONFIGURE
    Set to ``0`` / ``false`` / ``no`` to skip this setup (e.g. tests or custom handlers).
"""

from __future__ import annotations

import logging
import os
import sys


def _parse_level(name: str) -> int:
    level = getattr(logging, name.upper(), None)
    if isinstance(level, int):
        return level
    return logging.DEBUG


def _should_skip() -> bool:
    v = os.environ.get("ASTROMESH_LOG_CONFIGURE", "").lower()
    return v in ("0", "false", "no", "skip")


def setup_logging() -> None:
    """Configure the ``astromesh`` logger hierarchy; idempotent."""
    if _should_skip():
        return

    level = _parse_level(os.environ.get("ASTROMESH_LOG_LEVEL", "DEBUG"))
    third = _parse_level(os.environ.get("ASTROMESH_LOG_THIRDPARTY_LEVEL", "WARNING"))

    fmt = os.environ.get(
        "ASTROMESH_LOG_FORMAT",
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    datefmt = os.environ.get("ASTROMESH_LOG_DATEFMT", "%Y-%m-%dT%H:%M:%S")
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    astromesh = logging.getLogger("astromesh")
    astromesh.setLevel(level)

    if not astromesh.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(formatter)
        handler.setLevel(level)
        astromesh.addHandler(handler)

    astromesh.propagate = False

    for name in (
        "httpx",
        "httpcore",
        "h11",
        "openai",
        "urllib3",
        "asyncio",
    ):
        logging.getLogger(name).setLevel(third)
