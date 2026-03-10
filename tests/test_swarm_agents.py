import json
import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock

from astromesh.orchestration.swarm import SwarmPattern


@dataclass
class CompletionResponse:
    content: str
    tool_calls: list | None = None


def make_response(content, tool_calls=None):
    return CompletionResponse(content=content, tool_calls=tool_calls)


class TestSwarmWithAgentTools:
    @pytest.mark.asyncio
    async def test_swarm_handoff_via_tool_fn(self):
        """Swarm handoff should invoke the target agent via tool_fn."""
        handoff_json = json.dumps(
            {"handoff": "specialist", "context": "Need expert analysis"}
        )
        model_fn = AsyncMock(
            side_effect=[
                make_response(handoff_json),
                make_response("Expert analysis complete."),
            ]
        )
        tool_fn = AsyncMock(
            return_value={"answer": "Specialist context loaded", "steps": []}
        )

        pattern = SwarmPattern(agent_configs={"specialist": "specialist-agent"})
        result = await pattern.execute(
            query="Analyze this data",
            context={},
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=[],
        )

        tool_fn.assert_called_once_with(
            "specialist", {"query": "Need expert analysis"}
        )
        assert result["answer"] == "Expert analysis complete."

    @pytest.mark.asyncio
    async def test_swarm_no_handoff_returns_directly(self):
        """If no handoff, swarm returns the agent's direct answer."""
        model_fn = AsyncMock(return_value=make_response("Direct answer."))
        tool_fn = AsyncMock()

        pattern = SwarmPattern()
        result = await pattern.execute(
            query="Simple question",
            context={},
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=[],
        )

        assert result["answer"] == "Direct answer."
        tool_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_swarm_multiple_handoffs(self):
        """Chain of handoffs: A -> B -> C -> final answer."""
        model_fn = AsyncMock(
            side_effect=[
                make_response(
                    json.dumps({"handoff": "agent-b", "context": "step 1"})
                ),
                make_response(
                    json.dumps({"handoff": "agent-c", "context": "step 2"})
                ),
                make_response("Final from agent-c."),
            ]
        )
        tool_fn = AsyncMock(
            side_effect=[
                {"answer": "B loaded", "steps": []},
                {"answer": "C loaded", "steps": []},
            ]
        )

        pattern = SwarmPattern(
            agent_configs={"agent-b": "agent-b", "agent-c": "agent-c"}
        )
        result = await pattern.execute(
            query="Multi-step task",
            context={},
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=[],
        )

        assert tool_fn.call_count == 2
        assert result["answer"] == "Final from agent-c."
        assert result["final_agent"] == "agent-c"

    @pytest.mark.asyncio
    async def test_swarm_tool_calls_still_work(self):
        """Regular tool calls (non-handoff) still work within swarm."""
        tool_call = {"id": "tc_1", "name": "web_search", "arguments": {"q": "test"}}
        model_fn = AsyncMock(
            side_effect=[
                make_response("Searching...", tool_calls=[tool_call]),
                make_response("Found the answer."),
            ]
        )
        tool_fn = AsyncMock(return_value={"results": ["result1"]})

        pattern = SwarmPattern()
        result = await pattern.execute(
            query="Search for something",
            context={},
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=[],
        )

        assert result["answer"] == "Found the answer."
