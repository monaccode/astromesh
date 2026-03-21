import logging

import pytest

from astromesh.logging_config import setup_logging


@pytest.fixture
def fresh_astromesh_logger(monkeypatch):
    """Isolate astromesh logger between tests."""
    log = logging.getLogger("astromesh")
    log.handlers.clear()
    log.setLevel(logging.NOTSET)
    log.propagate = True
    yield log
    log.handlers.clear()
    log.setLevel(logging.NOTSET)
    log.propagate = True


def test_setup_logging_default_debug(fresh_astromesh_logger, monkeypatch):
    monkeypatch.delenv("ASTROMESH_LOG_CONFIGURE", raising=False)
    monkeypatch.delenv("ASTROMESH_LOG_LEVEL", raising=False)
    setup_logging()
    assert logging.getLogger("astromesh").level == logging.DEBUG


def test_setup_logging_respects_level(fresh_astromesh_logger, monkeypatch):
    monkeypatch.delenv("ASTROMESH_LOG_CONFIGURE", raising=False)
    monkeypatch.setenv("ASTROMESH_LOG_LEVEL", "WARNING")
    setup_logging()
    assert logging.getLogger("astromesh").level == logging.WARNING


def test_setup_logging_skipped_when_disabled(fresh_astromesh_logger, monkeypatch):
    monkeypatch.setenv("ASTROMESH_LOG_CONFIGURE", "0")
    setup_logging()
    assert not logging.getLogger("astromesh").handlers
