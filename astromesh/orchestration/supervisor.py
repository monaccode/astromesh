from astromesh.orchestration.patterns import OrchestrationPattern, AgentStep
import json as json_mod


class SupervisorPattern(OrchestrationPattern):
    """Supervisor delegates to worker sub-agents and coordinates."""

    def __init__(self, workers: dict | None = None):
        self._workers = workers or {}

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        steps = []
        worker_names = list(self._workers.keys()) or ["default"]

        for iteration in range(max_iterations):
            supervisor_prompt = (
                f"You are a supervisor managing workers: {worker_names}\n"
                f"Task: {query}\n"
                f"Previous steps: {[s.result or s.observation for s in steps]}\n"
                f'Decide: delegate to a worker (respond with JSON {{"delegate": "worker_name", "task": "..."}})'
                f' or provide final answer (respond with JSON {{"final_answer": "..."}})'
            )

            response = await model_fn([{"role": "user", "content": supervisor_prompt}], tools)

            try:
                decision = json_mod.loads(response.content)
            except json_mod.JSONDecodeError:
                steps.append(AgentStep(result=response.content))
                return {"answer": response.content, "steps": steps}

            if "final_answer" in decision:
                steps.append(AgentStep(result=decision["final_answer"]))
                return {"answer": decision["final_answer"], "steps": steps}

            if "delegate" in decision:
                worker_task = decision.get("task", query)
                worker_resp = await model_fn([{"role": "user", "content": worker_task}], tools)
                steps.append(
                    AgentStep(
                        thought=f"Delegated to {decision['delegate']}: {worker_task}",
                        result=worker_resp.content,
                    )
                )

        return {"answer": "Max iterations reached", "steps": steps}
