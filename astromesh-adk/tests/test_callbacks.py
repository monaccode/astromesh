import pytest
from astromesh_adk.callbacks import Callbacks


class RecordingCallbacks(Callbacks):
    def __init__(self):
        self.events = []

    async def on_step(self, step):
        self.events.append(("step", step))

    async def on_tool_result(self, tool_name, args, result):
        self.events.append(("tool_result", tool_name, result))

    async def on_model_call(self, model, messages, response):
        self.events.append(("model_call", model))

    async def on_error(self, error, context):
        self.events.append(("error", str(error)))


async def test_callbacks_are_noop_by_default():
    cb = Callbacks()
    # These should not raise
    await cb.on_step({})
    await cb.on_tool_result("tool", {}, "result")
    await cb.on_model_call("model", [], {})
    await cb.on_error(Exception("test"), {})


async def test_recording_callbacks():
    cb = RecordingCallbacks()
    await cb.on_step({"action": "search"})
    await cb.on_tool_result("web_search", {"q": "test"}, "result")
    assert len(cb.events) == 2
    assert cb.events[0] == ("step", {"action": "search"})
    assert cb.events[1][0] == "tool_result"
