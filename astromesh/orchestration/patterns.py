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


# Topes de los patrones: más pasos/subtareas que esto se recortan.
MAX_PASOS_PLAN = 6
MAX_SUBTAREAS = 4


class PlanAndExecutePattern(OrchestrationPattern):
    """Arma un plan, ejecuta cada paso con su ciclo de tools y sintetiza."""

    consumes_turn_context = True

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        conversacion = mensajes_de_conversacion(query, context)
        plan_response = await model_fn(
            [
                *conversacion,
                {
                    "role": "user",
                    "content": (
                        "Armá un plan paso a paso para responder el último mensaje. "
                        'Devolvé JSON: {"steps": [{"step": 1, "description": "..."}]}'
                    ),
                },
            ],
            tools,
            role="planner",
        )
        try:
            steps_plan = _loads(plan_response.content).get("steps", [])
        except (json_mod.JSONDecodeError, AttributeError, KeyError, ValueError):
            steps_plan = []
        # El modelo puede devolver pasos como strings, o `steps` que no es lista.
        if not isinstance(steps_plan, list):
            steps_plan = []
        steps_plan = [
            p if isinstance(p, dict) else {"step": i, "description": str(p)}
            for i, p in enumerate(steps_plan, 1)
        ]
        if not steps_plan:
            steps_plan = [{"step": 1, "description": "Responder el último mensaje."}]
        steps_plan = steps_plan[:MAX_PASOS_PLAN]

        steps: list[AgentStep] = []
        results: list[dict] = []
        for step_info in steps_plan:
            paso = await ciclo_de_tools(
                [
                    {
                        "role": "user",
                        "content": (
                            f"Ejecutá el paso {step_info.get('step')}: "
                            f"{step_info.get('description') or str(step_info)}\n"
                            f"Resultados anteriores: {results}"
                        ),
                    }
                ],
                model_fn,
                tool_fn,
                tools,
                max_iterations,
                role="worker",
            )
            results.append({"step": step_info.get("step"), "result": paso["answer"]})
            steps.extend(paso["steps"])

        final = await model_fn(
            [
                *conversacion,
                {
                    "role": "user",
                    "content": f"Con estos resultados, respondé el último mensaje: {results}",
                },
            ],
            [],
            role="synthesizer",
        )
        steps.append(AgentStep(result=final.content))
        return {"answer": final.content, "steps": steps, "plan": steps_plan}


class ParallelFanOutPattern(OrchestrationPattern):
    """Parte el último mensaje en subtareas en paralelo y las junta."""

    consumes_turn_context = True

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        conversacion = mensajes_de_conversacion(query, context)
        decompose_resp = await model_fn(
            [
                *conversacion,
                {
                    "role": "user",
                    "content": (
                        "Partí el último mensaje en 2 a 4 subtareas independientes "
                        "(una lista JSON de strings)."
                    ),
                },
            ],
            [],
            role="planner",
        )
        try:
            subtasks = _loads(decompose_resp.content)
            if not isinstance(subtasks, list) or not subtasks:
                subtasks = ["Responder el último mensaje."]
        # El modelo puede devolver cualquier cosa: sin lista, una sola subtarea.
        except Exception:  # noqa: BLE001
            subtasks = ["Responder el último mensaje."]
        subtasks = subtasks[:MAX_SUBTAREAS]

        async def run_subtask(subtask):
            r = await ciclo_de_tools(
                [{"role": "user", "content": str(subtask)}],
                model_fn,
                tool_fn,
                tools,
                max_iterations,
                role="worker",
            )
            return {"subtask": str(subtask), "result": r["answer"], "steps": r["steps"]}

        # TaskGroup: el primer error cancela las demás subtareas (cada una corre tools).
        try:
            async with aio.TaskGroup() as tg:
                tareas = [tg.create_task(run_subtask(st)) for st in subtasks]
        except* Exception as eg:  # noqa: BLE001  (se re-lanza la original)
            raise eg.exceptions[0] from None
        results = [t.result() for t in tareas]
        resumen = [{"subtask": r["subtask"], "result": r["result"]} for r in results]
        final = await model_fn(
            [
                *conversacion,
                {
                    "role": "user",
                    "content": (
                        "Juntá estos resultados en una respuesta al último mensaje:\n"
                        f"{json_mod.dumps(resumen, ensure_ascii=False)}"
                    ),
                },
            ],
            [],
            role="synthesizer",
        )
        steps = [s for r in results for s in r["steps"]]
        steps.append(AgentStep(result=final.content))
        return {"answer": final.content, "steps": steps, "subtasks": resumen}


class PipelinePattern(OrchestrationPattern):
    """Etapas en orden: la respuesta de una etapa es la entrada de la siguiente."""

    consumes_turn_context = True

    def __init__(self, stages: list[str] | None = None):
        self._stages = stages or ["analyze", "process", "synthesize"]

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        conversacion = mensajes_de_conversacion(query, context)
        current_input = None
        steps: list[AgentStep] = []
        for stage in self._stages:
            if current_input is None:
                messages = [
                    *conversacion,
                    {
                        "role": "user",
                        "content": (
                            f"Etapa «{stage}»: procesá el último mensaje y producí la "
                            "entrada de la etapa siguiente."
                        ),
                    },
                ]
            else:
                messages = [
                    {
                        "role": "user",
                        "content": (
                            f"Etapa «{stage}»: procesá esta entrada y producí la de la "
                            f"etapa siguiente.\nEntrada: {current_input}"
                        ),
                    }
                ]
            r = await ciclo_de_tools(
                messages, model_fn, tool_fn, tools, max_iterations, role=f"stage:{stage}"
            )
            steps.extend(r["steps"])
            current_input = r["answer"]
        return {"answer": current_input, "steps": steps}
