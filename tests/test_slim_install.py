# tests/test_slim_install.py
"""The API must import on a slim install — with no optional extras present.

astromesh-os builds its image .deb with only the `observability` extra, so the RAG and
SQLite dependencies are absent. `astromesh.api.main` eagerly imports the RAG and workflow
routes, so an eager `import numpy` / `import aiosqlite` down that chain means the daemon
cannot even start. The astromesh-os boot gate caught exactly that:

    astromeshd[864]: ModuleNotFoundError: No module named 'numpy'

Optional backends must import their heavy dependencies lazily, at call time. This test
fails on any import-time regression of that rule, without needing a slim env to run in.
"""

import builtins
import importlib
import sys

import pytest

# Third-party roots that live in optional extras (or are only transitively present) and so
# must never be imported at astromesh import time.
OPTIONAL_ROOTS = ("numpy", "faiss", "aiosqlite", "asyncpg", "chromadb", "qdrant_client")


@pytest.fixture
def slim_install(monkeypatch):
    """Simulate an install where no optional extra is available."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.split(".")[0] in OPTIONAL_ROOTS:
            raise ModuleNotFoundError(f"No module named '{name.split('.')[0]}'")
        return real_import(name, *args, **kwargs)

    # Force a real re-import of astromesh under the restricted importer.
    for mod in list(sys.modules):
        root = mod.split(".")[0]
        if root == "astromesh" or root in OPTIONAL_ROOTS:
            monkeypatch.delitem(sys.modules, mod, raising=False)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_api_main_imports_without_optional_extras(slim_install):
    """The astromesh-os boot path: astromeshd does `from astromesh.api.main import app`."""
    importlib.import_module("astromesh.api.main")


@pytest.mark.parametrize(
    "target",
    [
        "astromesh.rag.stores.faiss_store",
        "astromesh.rag.factory",
        "astromesh.api.routes.rag",
        "astromesh.workflow.store",
        "astromesh.api.routes.workflows",
    ],
)
def test_module_imports_without_optional_extras(slim_install, target):
    importlib.import_module(target)


def test_optional_backends_construct_without_their_extra(slim_install):
    """Constructing must stay cheap — only the actual I/O calls may need the extra."""
    faiss_store = importlib.import_module("astromesh.rag.stores.faiss_store")
    store = importlib.import_module("astromesh.workflow.store")

    assert faiss_store.FAISSStore(dimensions=8) is not None
    assert store.SqliteRunStore(db_path=":memory:") is not None
