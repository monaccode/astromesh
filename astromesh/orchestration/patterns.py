from abc import ABC, abstractmethod
import asyncio as aio
from dataclasses import dataclass
import json as json_mod


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


class PlanAndExecutePattern(OrchestrationPattern):
    """Create plan, then execute each step sequentially."""

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        # Step 1: Ask model to create a plan
        plan_prompt = f"Create a step-by-step plan to answer: {query}\nReturn JSON: {{\"steps\": [{{\"step\": 1, \"description\": \"...\", \"tool\": null, \"depends_on\": []}}]}}"
        plan_response = await model_fn([{"role": "user", "content": plan_prompt}], tools)

        try:
            plan = json_mod.loads(plan_response.content)
            steps_plan = plan.get("steps", [])
        except (json_mod.JSONDecodeError, KeyError):
            steps_plan = [{"step": 1, "description": query, "tool": None}]

        # Step 2: Execute each step
        steps = []
        results = []
        for step_info in steps_plan:
            step_query = f"Execute step {step_info['step']}: {step_info['description']}\nPrevious results: {results}"
            step_response = await model_fn([{"role": "user", "content": step_query}], tools)

            if step_response.tool_calls:
                for tc in step_response.tool_calls:
                    obs = await tool_fn(tc["name"], tc["arguments"])
                    results.append({"step": step_info["step"], "result": str(obs)})
                    steps.append(AgentStep(thought=step_response.content, action=tc["name"],
                        action_input=tc["arguments"], observation=str(obs)))
            else:
                results.append({"step": step_info["step"], "result": step_response.content})
                steps.append(AgentStep(result=step_response.content))

        # Step 3: Synthesize final answer
        synthesis_prompt = f"Synthesize a final answer from these results: {results}\nOriginal question: {query}"
        final = await model_fn([{"role": "user", "content": synthesis_prompt}], [])
        steps.append(AgentStep(result=final.content))

        return {"answer": final.content, "steps": steps, "plan": steps_plan}


class ParallelFanOutPattern(OrchestrationPattern):
    """Fan out subtasks in parallel, then aggregate."""

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        # Decompose into subtasks
        decompose_prompt = f"Decompose this into 2-4 independent subtasks (JSON list of strings): {query}"
        decompose_resp = await model_fn([{"role": "user", "content": decompose_prompt}], [])

        try:
            subtasks = json_mod.loads(decompose_resp.content)
            if not isinstance(subtasks, list):
                subtasks = [query]
        except json_mod.JSONDecodeError:
            subtasks = [query]

        # Execute subtasks in parallel
        async def run_subtask(subtask):
            resp = await model_fn([{"role": "user", "content": subtask}], tools)
            return {"subtask": subtask, "result": resp.content}

        results = await aio.gather(*[run_subtask(st) for st in subtasks])

        # Aggregate
        agg_prompt = f"Aggregate these results into a final answer:\n{json_mod.dumps(list(results))}\nOriginal question: {query}"
        final = await model_fn([{"role": "user", "content": agg_prompt}], [])

        steps = [AgentStep(thought=f"Subtask: {r['subtask']}", result=r["result"]) for r in results]
        steps.append(AgentStep(result=final.content))

        return {"answer": final.content, "steps": steps, "subtasks": list(results)}


class PipelinePattern(OrchestrationPattern):
    """Sequential pipeline: output of step N feeds into step N+1."""

    def __init__(self, stages: list[str] | None = None):
        self._stages = stages or ["analyze", "process", "synthesize"]

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        current_input = query
        steps = []

        for stage in self._stages:
            prompt = f"Stage '{stage}': Process the following input and produce output for the next stage.\nInput: {current_input}"
            response = await model_fn([{"role": "user", "content": prompt}], tools)

            if response.tool_calls:
                for tc in response.tool_calls:
                    obs = await tool_fn(tc["name"], tc["arguments"])
                    steps.append(AgentStep(thought=f"Stage: {stage}", action=tc["name"],
                        action_input=tc["arguments"], observation=str(obs)))
                    current_input = str(obs)
            else:
                steps.append(AgentStep(thought=f"Stage: {stage}", result=response.content))
                current_input = response.content

        return {"answer": current_input, "steps": steps}
