from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AgentStep:
    thought: str | None = None
    action: str | None = None
    action_input: dict | None = None
    observation: str | None = None
    result: str | None = None


class OrchestrationPattern(ABC):
    @abstractmethod
    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10) -> dict: ...


class ReActPattern(OrchestrationPattern):
    """Thought -> Action -> Observation loop."""

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        messages = [{"role": "user", "content": query}]
        steps: list[AgentStep] = []
        for _ in range(max_iterations):
            response = await model_fn(messages, tools)
            if response.tool_calls:
                for tc in response.tool_calls:
                    observation = await tool_fn(tc["name"], tc["arguments"])
                    steps.append(
                        AgentStep(
                            thought=response.content,
                            action=tc["name"],
                            action_input=tc["arguments"],
                            observation=str(observation),
                        )
                    )
                    messages.append(
                        {
                            "role": "assistant",
                            "content": response.content,
                            "tool_calls": [tc],
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "content": str(observation),
                            "tool_call_id": tc["id"],
                        }
                    )
            else:
                steps.append(AgentStep(result=response.content))
                return {"answer": response.content, "steps": steps}
        return {"answer": "Max iterations reached", "steps": steps}
