from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from astromesh.orchestration.supervisor import SupervisorPattern


@dataclass
class CompletionResponse:
    content: str
    tool_calls: list | None = None


def make_response(content, tool_calls=None):
    return CompletionResponse(content=content, tool_calls=tool_calls)


def _tool(name):
    return {
        "type": "function",
        "function": {"name": name, "description": "", "parameters": {"type": "object"}},
    }


def _call(i, name, query):
    return {"id": f"t{i}", "name": name, "arguments": {"query": query}}


class TestSupervisorWithAgentTools:
    @pytest.mark.asyncio
    async def test_supervisor_delegates_via_tool_fn(self):
        """El supervisor delega con una tool call nativa y contesta con lo que juntó."""
        model_fn = AsyncMock(
            side_effect=[
                make_response("", [_call(1, "qualify-lead", "Check Acme")]),
                make_response("Acme is qualified"),
            ]
        )
        tool_fn = AsyncMock(return_value={"answer": "Lead score: 85", "steps": []})

        pattern = SupervisorPattern(workers=["qualify-lead"])
        result = await pattern.execute(
            "Qualify Acme Corp", {}, model_fn, tool_fn, [_tool("qualify-lead")]
        )

        tool_fn.assert_called_once_with("qualify-lead", {"query": "Check Acme"})
        assert result["answer"] == "Acme is qualified"

    @pytest.mark.asyncio
    async def test_supervisor_final_answer_no_delegation(self):
        model_fn = AsyncMock(return_value=make_response("Already done"))
        tool_fn = AsyncMock()

        result = await SupervisorPattern().execute("Simple task", {}, model_fn, tool_fn, [])

        assert result["answer"] == "Already done"
        tool_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_supervisor_multiple_delegations(self):
        model_fn = AsyncMock(
            side_effect=[
                make_response("", [_call(1, "researcher", "Research X")]),
                make_response("", [_call(2, "writer", "Write about X")]),
                make_response("Here is the report"),
            ]
        )
        tool_fn = AsyncMock(
            side_effect=[
                {"answer": "Research results", "steps": []},
                {"answer": "Draft written", "steps": []},
            ]
        )

        pattern = SupervisorPattern(workers=["researcher", "writer"])
        result = await pattern.execute(
            "Write a report on X", {}, model_fn, tool_fn, [_tool("researcher"), _tool("writer")]
        )

        assert tool_fn.call_count == 2
        assert result["answer"] == "Here is the report"
