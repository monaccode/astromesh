import json
import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock

from astromesh.orchestration.supervisor import SupervisorPattern


@dataclass
class CompletionResponse:
    content: str
    tool_calls: list | None = None


def make_response(content, tool_calls=None):
    return CompletionResponse(content=content, tool_calls=tool_calls)


class TestSupervisorWithAgentTools:
    @pytest.mark.asyncio
    async def test_supervisor_delegates_via_tool_fn(self):
        """Supervisor should call tool_fn for agent tool delegation."""
        delegate_json = json.dumps({"delegate": "qualify-lead", "task": "Check Acme"})
        final_json = json.dumps({"final_answer": "Acme is qualified"})

        model_fn = AsyncMock(
            side_effect=[
                make_response(delegate_json),
                make_response(final_json),
            ]
        )
        tool_fn = AsyncMock(return_value={"answer": "Lead score: 85", "steps": []})
        agent_tools = [
            {
                "type": "function",
                "function": {
                    "name": "qualify-lead",
                    "description": "Qualify a lead",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        pattern = SupervisorPattern(workers={"qualify-lead": "sales-qualifier"})
        result = await pattern.execute(
            query="Qualify Acme Corp",
            context={},
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=agent_tools,
        )

        tool_fn.assert_called_once_with("qualify-lead", {"query": "Check Acme"})
        assert result["answer"] == "Acme is qualified"

    @pytest.mark.asyncio
    async def test_supervisor_final_answer_no_delegation(self):
        """Supervisor returns immediately if model gives final_answer."""
        final_json = json.dumps({"final_answer": "Already done"})
        model_fn = AsyncMock(return_value=make_response(final_json))
        tool_fn = AsyncMock()

        pattern = SupervisorPattern()
        result = await pattern.execute(
            query="Simple task",
            context={},
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=[],
        )

        assert result["answer"] == "Already done"
        tool_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_supervisor_multiple_delegations(self):
        """Supervisor can delegate to multiple agent tools in sequence."""
        model_fn = AsyncMock(
            side_effect=[
                make_response(
                    json.dumps({"delegate": "researcher", "task": "Research X"})
                ),
                make_response(
                    json.dumps({"delegate": "writer", "task": "Write about X"})
                ),
                make_response(json.dumps({"final_answer": "Here is the report"})),
            ]
        )
        tool_fn = AsyncMock(
            side_effect=[
                {"answer": "Research results", "steps": []},
                {"answer": "Draft written", "steps": []},
            ]
        )

        pattern = SupervisorPattern(
            workers={"researcher": "research-agent", "writer": "writer-agent"}
        )
        result = await pattern.execute(
            query="Write a report on X",
            context={},
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=[],
        )

        assert tool_fn.call_count == 2
        assert result["answer"] == "Here is the report"
