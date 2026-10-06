import asyncio as aio
import json as json_mod
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

try:
    from astromesh._native import rust_json_loads as _native_json_loads
except ImportError:
    _native_json_loads = None


def _loads(text):
    if _native_json_loads is not None and not os.environ.get("ASTROMESH_FORCE_PYTHON"):
        return _native_json_loads(text)
    return json_mod.loads(text)


def with_turn_context(query, turn_context):
    """La query del usuario con el contexto del turno adelante, o intacta si no hay.

    El contexto (`prompts.context`: RAG, prefetch) cambia en cada query, así que va
    al FINAL de la conversación, pegado al mensaje actual: todo lo anterior queda
    como prefijo estable para el caché del proveedor. Una query multimodal es una
    lista de partes; el contexto entra como una parte de texto más, adelante.
    """
    if not turn_context:
        return query
    if isinstance(query, list):
        return [{"type": "text", "text": turn_context}, *query]
    return f"{turn_context}\n\n{query}"


@dataclass
class AgentStep:
    thought: str | None = None
    action: str | None = None
    action_input: dict | None = None
    observation: str | None = None
    result: str | None = None


def mensajes_de_conversacion(query, context):
    """El historial y el mensaje actual, con el contexto del turno adelante.

    Lo comparten todos los patrones conversacionales: desde 0.64.0 el historial
    viaja como mensajes (`engine.py`, `_history_messages`) y un patrón que no lo
    lee contesta cada mensaje como si fuera el primero.
    """
    history = context.get("_history_messages", []) if isinstance(context, dict) else []
    turn_context = context.get("_turn_context") if isinstance(context, dict) else None
    return [
        *list(history),
        {"role": "user", "content": with_turn_context(query, turn_context)},
    ]


async def ciclo_de_tools(messages, model_fn, tool_fn, tools, max_iterations, role, permitidas=None):
    """Modelo → tools → resultado de vuelta al modelo, hasta una respuesta sin tools.

    `permitidas` acota qué tools se ejecutan: una fuera del set no llega a
    `tool_fn` y el modelo recibe una observación que lo dice (el supervisor sólo
    delega en sus trabajadores).
    """
    messages = list(messages)
    steps: list[AgentStep] = []
    for _ in range(max_iterations):
        response = await model_fn(messages, tools, role=role)
        if not response.tool_calls:
            steps.append(AgentStep(result=response.content))
            return {"answer": response.content, "steps": steps}
        # UN assistant con TODAS las tool_calls de esta respuesta, y
        # después un `tool` por cada una. Es la forma de OpenAI, y
        # además es la barata: antes se emitía un assistant POR
        # tool_call, y cada uno repetía el mismo `content` y el mismo
        # `reasoning_content`. En un modelo de razonamiento —Kimi k2.x,
        # el que corre toda la flota— el razonamiento es la parte más
        # larga del mensaje, así que tres tools en una respuesta lo
        # mandaban tres veces; y como el transcripto se re-manda entero
        # en cada vuelta siguiente, ese triple se volvía a pagar en
        # todas. Lo fija `test_react_agrupa_tool_calls_de_una_misma_respuesta`.
        #
        # Reshape the normalized internal tool_call back to OpenAI
        # format before echoing it to the LLM. Since 0.28.4 the
        # provider normalizes tool_calls to {id, name, arguments:dict}
        # for internal consumption — but the assistant.tool_calls
        # field sent over the wire MUST be the nested OpenAI shape
        # {id, type:"function", function:{name, arguments:<JSON
        # string>}}, or the API rejects the next request as 400.
        assistant_msg = {
            "role": "assistant",
            "content": response.content,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json_mod.dumps(tc["arguments"], ensure_ascii=False),
                    },
                }
                for tc in response.tool_calls
            ],
        }
        # Thinking models (Kimi k2.5/k2.6 on Moonshot) require the
        # assistant's reasoning_content to be echoed back on the
        # tool-call message, or the next request 400s with
        # "reasoning_content is missing in assistant tool call message".
        reasoning = getattr(response, "reasoning_content", None)
        if reasoning:
            assistant_msg["reasoning_content"] = reasoning
        messages.append(assistant_msg)
        for tc in response.tool_calls:
            if permitidas is not None and tc["name"] not in permitidas:
                observation = f"La tool «{tc['name']}» no está disponible para este agente."
            else:
                observation = await tool_fn(tc["name"], tc["arguments"])
            steps.append(
                AgentStep(
                    thought=response.content,
                    action=tc["name"],
                    action_input=tc["arguments"],
                    observation=str(observation),
                )
            )
            messages.append({"role": "tool", "content": str(observation), "tool_call_id": tc["id"]})
    return {"answer": "Max iterations reached", "steps": steps}


class OrchestrationPattern(ABC):
    @abstractmethod
    async def execute(
        self, query, context, model_fn, tool_fn, tools, max_iterations=10
    ) -> dict: ...


class ReActPattern(OrchestrationPattern):
    """Thought -> Action -> Observation loop."""

    consumes_turn_context = True

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        return await ciclo_de_tools(
            mensajes_de_conversacion(query, context),
            model_fn,
            tool_fn,
            tools,
            max_iterations,
            role="reasoner",
        )


class PlanAndExecutePattern(OrchestrationPattern):
    """Create plan, then execute each step sequentially."""

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        # Step 1: Ask model to create a plan
        plan_prompt = f'Create a step-by-step plan to answer: {query}\nReturn JSON: {{"steps": [{{"step": 1, "description": "...", "tool": null, "depends_on": []}}]}}'
        plan_response = await model_fn(
            [{"role": "user", "content": plan_prompt}], tools, role="planner"
        )

        try:
            plan = _loads(plan_response.content)
            steps_plan = plan.get("steps", [])
        except (json_mod.JSONDecodeError, KeyError, ValueError):
            steps_plan = [{"step": 1, "description": query, "tool": None}]

        # Step 2: Execute each step
        steps = []
        results = []
        for step_info in steps_plan:
            step_query = f"Execute step {step_info['step']}: {step_info['description']}\nPrevious results: {results}"
            step_response = await model_fn(
                [{"role": "user", "content": step_query}], tools, role="worker"
            )

            if step_response.tool_calls:
                for tc in step_response.tool_calls:
                    obs = await tool_fn(tc["name"], tc["arguments"])
                    results.append({"step": step_info["step"], "result": str(obs)})
                    steps.append(
                        AgentStep(
                            thought=step_response.content,
                            action=tc["name"],
                            action_input=tc["arguments"],
                            observation=str(obs),
                        )
                    )
            else:
                results.append({"step": step_info["step"], "result": step_response.content})
                steps.append(AgentStep(result=step_response.content))

        # Step 3: Synthesize final answer
        synthesis_prompt = (
            f"Synthesize a final answer from these results: {results}\nOriginal question: {query}"
        )
        final = await model_fn(
            [{"role": "user", "content": synthesis_prompt}], [], role="synthesizer"
        )
        steps.append(AgentStep(result=final.content))

        return {"answer": final.content, "steps": steps, "plan": steps_plan}


class ParallelFanOutPattern(OrchestrationPattern):
    """Fan out subtasks in parallel, then aggregate."""

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        # Decompose into subtasks
        decompose_prompt = (
            f"Decompose this into 2-4 independent subtasks (JSON list of strings): {query}"
        )
        decompose_resp = await model_fn(
            [{"role": "user", "content": decompose_prompt}], [], role="planner"
        )

        try:
            subtasks = _loads(decompose_resp.content)
            if not isinstance(subtasks, list):
                subtasks = [query]
        # El modelo puede devolver cualquier cosa: si no es una lista de subtareas
        # se sigue con la consulta original. Decía `(JSONDecodeError, Exception)`,
        # una tupla donde el segundo miembro ya cubría al primero.
        except Exception:  # noqa: BLE001
            subtasks = [query]

        # Execute subtasks in parallel
        async def run_subtask(subtask):
            resp = await model_fn([{"role": "user", "content": subtask}], tools, role="worker")
            return {"subtask": subtask, "result": resp.content}

        results = await aio.gather(*[run_subtask(st) for st in subtasks])

        # Aggregate
        agg_prompt = f"Aggregate these results into a final answer:\n{json_mod.dumps(list(results))}\nOriginal question: {query}"
        final = await model_fn([{"role": "user", "content": agg_prompt}], [], role="synthesizer")

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
            response = await model_fn(
                [{"role": "user", "content": prompt}], tools, role=f"stage:{stage}"
            )

            if response.tool_calls:
                for tc in response.tool_calls:
                    obs = await tool_fn(tc["name"], tc["arguments"])
                    steps.append(
                        AgentStep(
                            thought=f"Stage: {stage}",
                            action=tc["name"],
                            action_input=tc["arguments"],
                            observation=str(obs),
                        )
                    )
                    current_input = str(obs)
            else:
                steps.append(AgentStep(thought=f"Stage: {stage}", result=response.content))
                current_input = response.content

        return {"answer": current_input, "steps": steps}
