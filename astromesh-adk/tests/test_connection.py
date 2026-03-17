import pytest
from astromesh_adk.connection import (
    connect,
    disconnect,
    remote,
    get_connection,
    _connection_var,
)


def test_connect_sets_global():
    connect(url="https://test.astromesh.io", api_key="key123")
    conn = get_connection()
    assert conn is not None
    assert conn.url == "https://test.astromesh.io"
    assert conn.api_key == "key123"
    disconnect()


def test_disconnect_clears_global():
    connect(url="https://test.astromesh.io", api_key="key")
    disconnect()
    conn = get_connection()
    assert conn is None


async def test_remote_context_manager():
    async with remote("https://ctx.astromesh.io", api_key="ctx-key"):
        conn = get_connection()
        assert conn is not None
        assert conn.url == "https://ctx.astromesh.io"

    # After exiting, connection is restored to previous state
    conn = get_connection()
    assert conn is None


async def test_remote_restores_previous():
    connect(url="https://global.io", api_key="g")
    async with remote("https://scoped.io", api_key="s"):
        conn = get_connection()
        assert conn.url == "https://scoped.io"

    conn = get_connection()
    assert conn.url == "https://global.io"
    disconnect()


def test_connection_repr():
    connect(url="https://test.io", api_key="secret")
    conn = get_connection()
    r = repr(conn)
    assert "test.io" in r
    assert "secret" not in r  # API key should not be in repr
    disconnect()
