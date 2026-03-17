"""Remote Astromesh connection management."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass


@dataclass
class RemoteConnection:
    """Represents a connection to a remote Astromesh instance."""

    url: str
    api_key: str

    def __repr__(self):
        return f"RemoteConnection(url={self.url!r})"


# Module-level state (after class definition to avoid forward reference)
_connection_var: contextvars.ContextVar[RemoteConnection | None] = contextvars.ContextVar(
    "astromesh_adk_connection", default=None
)
_global_connection: RemoteConnection | None = None


def connect(url: str, api_key: str) -> None:
    """Set a global remote connection. All agent.run() calls will use this."""
    global _global_connection
    _global_connection = RemoteConnection(url=url, api_key=api_key)
    _connection_var.set(_global_connection)


def disconnect() -> None:
    """Clear the global remote connection. Agents will run locally."""
    global _global_connection
    _global_connection = None
    _connection_var.set(None)


def get_connection() -> RemoteConnection | None:
    """Get the current connection (contextvar > global > None)."""
    return _connection_var.get(None)


class remote:
    """Async context manager for scoped remote connections.

    Usage:
        async with remote("https://cluster.io", api_key="..."):
            result = await agent.run("query")  # runs on remote
        # Back to local after exiting
    """

    def __init__(self, url: str, api_key: str):
        self._connection = RemoteConnection(url=url, api_key=api_key)
        self._token: contextvars.Token | None = None

    async def __aenter__(self):
        self._token = _connection_var.set(self._connection)
        return self._connection

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._token is not None:
            _connection_var.reset(self._token)
        return False
