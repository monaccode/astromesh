import pytest

from astromesh_adk.agent import agent
from astromesh_adk.runner import ADKRuntime
from astromesh.core.memory import ConversationBackend
from astromesh.providers.base import CompletionResponse


class MemBackend(ConversationBackend):
    def __init__(self):
        self.store = {}

    async def save_turn(self, session_id, turn):
        self.store.setdefault(session_id, []).append(turn)

    async def get_history(self, session_id, limit=50):
        return self.store.get(session_id, [])[-limit:]

    async def clear(self, session_id):
        self.store.pop(session_id, None)

    async def get_summary(self, session_id):
        return None

    async def save_summary(self, session_id, summary):
        pass


class StubProvider:
    def __init__(self, sink):
        self._sink = sink

    async def complete(self, messages, **kwargs):
        self._sink.append(list(messages))
        return CompletionResponse(
            content="respuesta", model="stub", provider="stub", usage={},
            latency_ms=0.0, cost=0.0, tool_calls=[],
        )

    def estimated_cost(self, model, input_tokens, output_tokens):
        return 0.0

    def supports_tools(self):
        return True

    def supports_vision(self):
        return False


@pytest.mark.asyncio
async def test_runner_persists_and_injects_history(monkeypatch):
    backend = MemBackend()
    monkeypatch.setattr(
        "astromesh.memory.factory.build_conversation_backend", lambda cfg: backend
    )
    seen_messages = []

    rt = ADKRuntime(provider_factory=lambda pname, mname, cfg: StubProvider(seen_messages))

    @agent(
        name="astro", model="claude-haiku-4-5", pattern="react",
        memory={"conversational": {"backend": "redis", "strategy": "sliding_window",
                                   "max_turns": 20, "connection": {"url": "redis://x"}}},
    )
    async def astro(ctx):
        return None

    # First turn: nothing to inject; persists user+assistant.
    await rt.run_agent(astro, "primera", session_id="org1:user1")
    assert [t.role for t in backend.store["org1:user1"]] == ["user", "assistant"]
    assert backend.store["org1:user1"][0].content == "primera"
    assert backend.store["org1:user1"][1].content == "respuesta"

    # Second turn: prior turns injected into the LLM messages.
    seen_messages.clear()
    await rt.run_agent(astro, "segunda", session_id="org1:user1")
    first_call = seen_messages[0]
    # system prompt is prepended by model_fn, then history, then current query
    contents = [m["content"] for m in first_call]
    assert "primera" in contents
    assert "respuesta" in contents
    assert first_call[-1] == {"role": "user", "content": "segunda"}


@pytest.mark.asyncio
async def test_runner_without_memory_config_no_persist(monkeypatch):
    rt = ADKRuntime(provider_factory=lambda pname, mname, cfg: StubProvider([]))

    @agent(name="plain", model="claude-haiku-4-5", pattern="react")
    async def plain(ctx):
        return None

    # Must not raise and must not touch any backend.
    result = await rt.run_agent(plain, "hola", session_id="s1")
    assert result.answer == "respuesta"
