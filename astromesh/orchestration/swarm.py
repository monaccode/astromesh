from astromesh.orchestration.patterns import OrchestrationPattern, AgentStep
import json as json_mod


class SwarmPattern(OrchestrationPattern):
    """Agents hand off to each other based on context."""

    def __init__(self, agent_configs: dict | None = None):
        self._agents = agent_configs or {}

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        current_agent = "default"
        steps = []
        messages = [{"role": "user", "content": query}]

        for _ in range(max_iterations):
            agent_prompt = f"You are agent '{current_agent}'. Available agents to hand off to: {list(self._agents.keys()) or ['default']}\n"
            agent_prompt += 'Respond with your answer, or hand off with JSON {"handoff": "agent_name", "context": "..."}'

            full_messages = [{"role": "system", "content": agent_prompt}] + messages
            response = await model_fn(full_messages, tools)

            try:
                parsed = json_mod.loads(response.content)
                if "handoff" in parsed:
                    steps.append(
                        AgentStep(
                            thought=f"Agent '{current_agent}' hands off to '{parsed['handoff']}'",
                            result=parsed.get("context", ""),
                        )
                    )
                    current_agent = parsed["handoff"]
                    messages.append({"role": "assistant", "content": response.content})
                    continue
            except (json_mod.JSONDecodeError, KeyError):
                pass

            if response.tool_calls:
                for tc in response.tool_calls:
                    obs = await tool_fn(tc["name"], tc["arguments"])
                    steps.append(
                        AgentStep(
                            thought=response.content,
                            action=tc["name"],
                            action_input=tc["arguments"],
                            observation=str(obs),
                        )
                    )
                    messages.append({"role": "tool", "content": str(obs), "tool_call_id": tc["id"]})
            else:
                steps.append(AgentStep(result=response.content))
                return {"answer": response.content, "steps": steps, "final_agent": current_agent}

        return {"answer": "Max iterations reached", "steps": steps}
