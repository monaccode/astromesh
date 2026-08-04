"""Patrón de orquestación Glyph: el modelo emite un programa, el runtime lo ejecuta.

Este módulo importa `astromesh_glyph`, que es un extra opcional. Nadie debe
importarlo a nivel de módulo desde el core: `astromesh/api/main.py` tiene que
seguir importando sin extras instalados, porque eso es lo que hace bootear la
imagen de astromesh-os.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from astromesh_glyph import (
    CapabilitySpec,
    GlyphCompileError,
    GlyphExecutionError,
    GlyphSyntaxError,
    build_system_block,
    compile_program,
    execute,
    extract_program,
    parse,
)

from astromesh.orchestration.patterns import AgentStep, OrchestrationPattern

logger = logging.getLogger(__name__)

_ASK_SPEC = CapabilitySpec(
    name="ask",
    description=(
        "Consulta al modelo con un texto y un contexto opcional. Usala para pasos "
        "que requieren criterio: resumir, clasificar, redactar."
    ),
    parameters={
        "type": "object",
        "properties": {
            "prompt": {"type": "string"},
            "context": {"type": "object"},
        },
        "required": ["prompt"],
    },
    is_semantic=True,
)


class PatternCapabilities:
    """Adapta lo que recibe un patrón de orquestación al protocolo de Glyph.

    El spec la llamaba `ToolRegistryCapabilities`, pero el patrón nunca ve el
    `ToolRegistry`: ve los schemas ya filtrados por permisos y un `tool_fn` que
    ya aplica rate limits y aprobación. Envuelve esos dos, y agrega `ask` como
    capacidad sintética respaldada por `model_fn`.
    """

    def __init__(
        self,
        tools: list[dict[str, Any]],
        tool_fn: Callable[[str, dict], Any] | None,
        model_fn: Callable[..., Any] | None,
    ) -> None:
        self._tools = tools
        self._tool_fn = tool_fn
        self._model_fn = model_fn
        self.semantic_calls = 0

    def list_capabilities(self) -> list[CapabilitySpec]:
        # `returns` sale de una clave `function.returns` si el schema la trae.
        # `ToolDefinition` todavía no la declara, así que hoy sólo la pueblan los
        # schemas armados a mano (el benchmark). Mientras esté vacía, el modelo
        # tiene que adivinar los nombres de campo de lo que devuelve una tool —
        # y un campo inventado filtra a vacío en silencio, no da error.
        specs = [
            CapabilitySpec(
                name=fn["name"],
                description=fn.get("description", ""),
                parameters=fn.get("parameters") or {},
                returns=fn.get("returns", ""),
            )
            for tool in self._tools
            if (fn := tool.get("function"))
        ]
        specs.append(_ASK_SPEC)
        return specs

    async def invoke(self, name: str, args: dict[str, Any]) -> Any:
        if name == "ask":
            return await self._ask(args)
        return await self._tool_fn(name, args)

    async def _ask(self, args: dict[str, Any]) -> Any:
        self.semantic_calls += 1
        content = args["prompt"]
        if (context := args.get("context")) is not None:
            serialized = json.dumps(context, ensure_ascii=False, default=str)
            content = f"{content}\n\nContexto:\n{serialized}"
        # tools=[] a propósito: `ask` pide texto, no una acción. Ofrecerle tools
        # acá invita al modelo a abrir un loop dentro de un paso del programa.
        response = await self._model_fn([{"role": "user", "content": content}], [], role="default")
        return response.content


class GlyphPattern(OrchestrationPattern):
    """Un programa por corrida, en vez de una acción por vuelta.

    Dos llamadas al modelo en el caso feliz: una para que escriba el programa y
    otra para que redacte la respuesta con el resultado. Un ReAct equivalente
    gasta una por tool más la final.
    """

    def __init__(
        self, max_repairs: int = 2, narrate: bool = True, program: str | None = None
    ) -> None:
        self._max_repairs = max_repairs
        # `narrate=False` corta la segunda llamada al modelo y devuelve el
        # resultado del programa como JSON. Un agente encadenado consume
        # `output.data`, no prosa: pedirle al modelo que redacte algo que nadie
        # va a leer es una llamada entera de puro desperdicio.
        self._narrate = narrate
        # Un programa fijo salta la generación entera. Es donde está el 98% del
        # costo del patrón: el modelo reescribiendo el mismo programa en cada
        # corrida. Con esto, una corrida hace cero llamadas al modelo.
        # `max_repairs` se ignora en este modo — no hay nada que reparar, porque
        # un programa que no compila impide que el agente cargue.
        self._program = program

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        capabilities = PatternCapabilities(tools=tools, tool_fn=tool_fn, model_fn=model_fn)
        catalog = capabilities.list_capabilities()
        history = context.get("_history_messages", []) if isinstance(context, dict) else []
        caller_context = context.get("_caller_context", {}) if isinstance(context, dict) else {}
        # Las dos variables que ve un programa. Van siempre, aunque el programa no
        # las use: el compilador las acepta como predefinidas y no cuesta nada.
        env = {"query": query, "context": caller_context}

        steps: list[AgentStep] = []
        model_calls = 0
        repairs = 0
        result = None
        failure = None
        source = self._program or ""

        if self._program is not None:
            try:
                graph = compile_program(parse(source), catalog, predefined=env)
                result = await execute(graph, capabilities, initial_env=env)
            except (GlyphSyntaxError, GlyphCompileError, GlyphExecutionError) as exc:
                failure = exc
        else:
            # El bloque de gramática va **antes** de la consulta y en su propio
            # mensaje: es idéntico en cada corrida del agente, así que como
            # prefijo estable lo puede cachear el proveedor. Metido junto a la
            # consulta, cada query distinta rompía la coincidencia de prefijo.
            block = build_system_block(catalog)
            messages = [
                *list(history),
                {"role": "user", "content": block},
                {"role": "user", "content": query},
            ]
            # max_iterations describe vueltas de ReAct; acá no hay loop, así que
            # se reinterpreta como techo de intentos.
            budget = max(0, min(self._max_repairs, max_iterations - 1))

            while True:
                response = await model_fn(messages, [], role="reasoner")
                model_calls += 1
                source = extract_program(response.content or "")

                try:
                    graph = compile_program(parse(source), catalog, predefined=env)
                    result = await execute(graph, capabilities, initial_env=env)
                    break
                except (GlyphSyntaxError, GlyphCompileError, GlyphExecutionError) as exc:
                    failure = exc
                    if repairs >= budget:
                        break
                    repairs += 1
                    logger.info(
                        "glyph: reparación %d/%d tras %s", repairs, budget, type(exc).__name__
                    )
                    messages = [
                        *messages,
                        {"role": "assistant", "content": response.content},
                        {"role": "user", "content": _repair_prompt(exc)},
                    ]

        if result is None:
            answer = (
                f"No pudo ejecutarse el plan tras {repairs} reparación(es). Último error: {failure}"
            )
            steps.append(AgentStep(result=answer))
            return {
                "answer": answer,
                "steps": steps,
                "glyph": {
                    "model_calls": model_calls,
                    "capability_calls": 0,
                    "semantic_calls": capabilities.semantic_calls,
                    "repairs": repairs,
                    "failed": True,
                    "program": source,
                },
            }

        steps.extend(
            AgentStep(
                action=call.capability,
                action_input=call.args,
                observation=str(call.result) if call.ok else f"ERROR: {call.error}",
            )
            for call in result.calls
        )

        rendered = json.dumps(result.value, ensure_ascii=False, default=str)

        if not self._narrate:
            steps.append(AgentStep(result=rendered))
            return {
                "answer": rendered,
                "steps": steps,
                "glyph": {
                    "model_calls": model_calls,
                    "capability_calls": len(result.calls),
                    "semantic_calls": capabilities.semantic_calls,
                    "repairs": repairs,
                    "failed": False,
                    "program": source,
                },
            }

        # La narración NO lleva el bloque de gramática ni el catálogo: para
        # redactar la respuesta con el resultado no hacen falta, y arrastrarlos
        # duplicaba el costo fijo del patrón en cada corrida. Tampoco van los
        # mensajes de reparación, que sólo hablan de errores ya resueltos.
        final = await model_fn(
            [
                *list(history),
                {"role": "user", "content": query},
                {"role": "assistant", "content": f"Ejecuté este programa:\n{source}"},
                {
                    "role": "user",
                    "content": (
                        f"Resultado de la ejecución:\n{rendered}\n\n"
                        "Respondé la consulta original con este resultado."
                    ),
                },
            ],
            [],
            role="default",
        )
        model_calls += 1
        steps.append(AgentStep(result=final.content))

        return {
            "answer": final.content,
            "steps": steps,
            "glyph": {
                "model_calls": model_calls,
                "capability_calls": len(result.calls),
                "semantic_calls": capabilities.semantic_calls,
                "repairs": repairs,
                "failed": False,
                "program": source,
            },
        }


def _repair_prompt(exc: Exception) -> str:
    if isinstance(exc, GlyphExecutionError):
        return exc.partial.to_prompt()
    return (
        f"Ese programa no es válido: {exc}\n\n"
        "Corregilo y devolvé el programa completo de nuevo, en un bloque ```glyph."
    )
