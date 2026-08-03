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

from astromesh_glyph import CapabilitySpec

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
        specs = [
            CapabilitySpec(
                name=fn["name"],
                description=fn.get("description", ""),
                parameters=fn.get("parameters") or {},
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
