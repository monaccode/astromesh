from astromesh.runtime.engine import Agent


class _RecordingPromptEngine:
    def __init__(self):
        self.context = None

    def render(self, template, context):
        self.context = context
        return "SYSTEM"


class _StubPattern:
    async def execute(self, *a, **k):
        return {"answer": "ok"}


class _StubMemory:
    async def build_context(self, *a, **k):
        return ""

    async def persist_turn(self, *a, **k):
        return None


class _StubTools:
    def get_tool_schemas(self, *a, **k):
        return []


class _FakeRag:
    async def build_context(self, query_text):
        return f"KB::{query_text}"


def _runner(rag):
    pe = _RecordingPromptEngine()
    runner = Agent(
        name="a1",
        version="1",
        namespace="default",
        description="",
        routers={"default": None},
        memory=_StubMemory(),
        tools=_StubTools(),
        pattern=_StubPattern(),
        system_prompt="hola",
        prompt_engine=pe,
        guardrails={},
        permissions={},
        orchestration_config={},
        rag=rag,
    )
    return runner, pe


async def test_run_injects_knowledge_when_rag_present():
    runner, pe = _runner(_FakeRag())
    await runner.run("reembolsos", session_id="s1")
    assert pe.context["knowledge"] == "KB::reembolsos"


async def test_run_injects_empty_knowledge_when_no_rag():
    runner, pe = _runner(None)
    await runner.run("hola", session_id="s1")
    assert pe.context.get("knowledge", "") == ""
