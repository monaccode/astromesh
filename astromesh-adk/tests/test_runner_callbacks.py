"""The ADK runner must invoke the Callbacks API during tool execution."""
from __future__ import annotations

import asyncio

from astromesh_adk.callbacks import Callbacks
from astromesh_adk.runner import ADKRuntime


def test_make_tool_fn_invokes_on_tool_result():
    """_make_tool_fn must call callbacks.on_tool_result after a tool runs."""
    seen: list[tuple] = []

    class Spy(Callbacks):
        async def on_tool_result(self, tool_name, args, result):
            seen.append((tool_name, args, result))

    async def echo(**kwargs):
        return {"echoed": kwargs}

    echo.tool_name = "echo"

    rt = ADKRuntime()
    tool_fn = rt._make_tool_fn([echo], tctx=None, callbacks=Spy())
    result = asyncio.run(tool_fn("echo", {"x": 1}))

    assert result == {"echoed": {"x": 1}}
    assert seen == [("echo", {"x": 1}, {"echoed": {"x": 1}})]


def test_make_tool_fn_callback_error_does_not_break_tool():
    """A callback that raises must not break tool execution."""

    class BadCallbacks(Callbacks):
        async def on_tool_result(self, tool_name, args, result):
            raise RuntimeError("buggy callback")

    async def echo(**kwargs):
        return {"ok": True}

    echo.tool_name = "echo"

    rt = ADKRuntime()
    tool_fn = rt._make_tool_fn([echo], tctx=None, callbacks=BadCallbacks())
    result = asyncio.run(tool_fn("echo", {}))

    assert result == {"ok": True}


def test_make_tool_fn_works_without_callbacks():
    """callbacks is optional — omitting it keeps the old behavior."""

    async def echo(**kwargs):
        return {"ok": True}

    echo.tool_name = "echo"

    rt = ADKRuntime()
    tool_fn = rt._make_tool_fn([echo], tctx=None)
    assert asyncio.run(tool_fn("echo", {})) == {"ok": True}
