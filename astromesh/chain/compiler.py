"""Compila `spec.chain` a un WorkflowSpec que el motor ya sabe ejecutar.

Se compila en bootstrap, no en runtime. Eso hace que un ciclo, un max_depth
excedido o un agente inexistente exploten al arrancar —con la ruta completa en
el mensaje— en vez de a mitad de una corrida en producción, y deja la cadena
expandida disponible para inspección sin ejecutar nada.
"""

from __future__ import annotations

import re

from astromesh.chain.models import ChainLink, ChainSpec
from astromesh.chain.naming import CHAIN_PREFIX, chain_workflow_name
from astromesh.workflow.models import RetryConfig, StepSpec, WorkflowSpec

__all__ = [
    "CHAIN_PREFIX",
    "chain_graph",
    "chain_workflow_name",
    "compile_chain",
]

# `output.` en una cadena refiere al agente inmediatamente anterior. En el
# contexto del workflow eso vive en `steps.<agente>.output`, así que se reescribe
# al compilar. Con borde de palabra para no tocar un `mi_output.x`.
_OUTPUT_REF = re.compile(r"\boutput\.")


def _chain_of(agent_name: str, agent_configs: dict) -> ChainSpec | None:
    config = agent_configs.get(agent_name)
    if not config:
        return None
    raw = (config.get("spec") or {}).get("chain")
    return ChainSpec.from_dict(raw) if raw else None


def _rebind(expr: str | None, padre: str) -> str | None:
    """Reescribe `output.x` a `steps.<padre>.output.x`."""
    if not expr:
        return expr
    return _OUTPUT_REF.sub(f"steps.{padre}.output.", expr)


def _step_name(padre: str, hijo: str) -> str:
    """Nombre único de paso: un mismo agente puede aparecer bajo dos padres."""
    return f"{padre}__{hijo}"


def compile_chain(agent_name: str, agent_configs: dict) -> WorkflowSpec | None:
    """Devuelve el WorkflowSpec de la cadena de `agent_name`, o None si no declara."""
    raiz = _chain_of(agent_name, agent_configs)
    if raiz is None:
        return None

    steps: list[StepSpec] = [
        StepSpec(name=agent_name, agent=agent_name, input_template="{{ trigger.query }}")
    ]
    _expandir(agent_name, raiz, agent_configs, steps, ruta=[agent_name], max_depth=raiz.max_depth)

    return WorkflowSpec(
        name=chain_workflow_name(agent_name),
        description=f"cadena compilada del agente '{agent_name}'",
        steps=steps,
    )


def _validar_destino(link: ChainLink, padre: str, ruta: list[str], agent_configs: dict) -> None:
    if link.agent not in agent_configs:
        raise ValueError(
            f"el agente '{link.agent}', referenciado por la cadena de '{padre}', no existe"
        )
    if link.agent in ruta:
        raise ValueError(
            f"cadena del agente '{ruta[0]}': ciclo detectado en la ruta "
            f"{' -> '.join([*ruta, link.agent])}"
        )


def _expandir(
    padre: str,
    chain: ChainSpec,
    agent_configs: dict,
    steps: list[StepSpec],
    ruta: list[str],
    max_depth: int,
) -> None:
    if len(ruta) > max_depth:
        raise ValueError(
            f"cadena del agente '{ruta[0]}': se excedió max_depth={max_depth} "
            f"en la ruta {' -> '.join(ruta)}"
        )

    normales = [link for link in chain.links if not link.default]
    default = next((link for link in chain.links if link.default), None)

    for link in normales:
        _validar_destino(link, padre, ruta, agent_configs)

    # Nombres de los pasos con guarda: el `default` se compila como la negación
    # de su disyunción, leída del slot `when` que el motor publica por paso.
    guardados = [_step_name(padre, link.agent) for link in normales if link.when]

    sub_steps = [_a_step(link, padre, _step_name(padre, link.agent)) for link in normales]
    if chain.mode == "parallel" and sub_steps:
        steps.append(StepSpec(name=f"{padre}__fanout", parallel=sub_steps))
    else:
        steps.extend(sub_steps)

    if default is not None:
        _validar_destino(default, padre, ruta, agent_configs)
        # El default va siempre como paso suelto, también en `parallel`: necesita
        # las guardas hermanas ya evaluadas para saber si le toca.
        paso = _a_step(default, padre, _step_name(padre, default.agent))
        if guardados:
            negacion = " or ".join(f"when['{n}']" for n in guardados)
            paso.when = f"{{{{ not ({negacion}) }}}}"
            paso.strict_conditions = True
        steps.append(paso)

    for link in [*normales, *([default] if default else [])]:
        anidada = _chain_of(link.agent, agent_configs)
        if anidada is not None:
            _expandir(
                link.agent,
                anidada,
                agent_configs,
                steps,
                ruta=[*ruta, link.agent],
                max_depth=max_depth,
            )


def _a_step(link: ChainLink, padre: str, nombre: str) -> StepSpec:
    return StepSpec(
        name=nombre,
        agent=link.agent,
        input_template=_rebind(link.input, padre),
        when=_rebind(link.when, padre),
        strict_conditions=link.when is not None,
        retry=RetryConfig(**link.retry) if link.retry else None,
        timeout_seconds=link.timeout_seconds,
        on_error=link.on_error,
    )


def chain_graph(agent_name: str, agent_configs: dict) -> dict | None:
    """El grafo expandido, sin ejecutar nada. Alimenta GET /v1/agents/{n}/chain."""
    raiz = _chain_of(agent_name, agent_configs)
    if raiz is None:
        return None

    links: list[dict] = []

    def recorrer(padre: str, chain: ChainSpec, ruta: list[str]) -> None:
        if len(ruta) > raiz.max_depth:
            return
        for link in chain.links:
            if link.agent in ruta:
                continue
            links.append(
                {
                    "agent": link.agent,
                    "depth": len(ruta),
                    "via": None if len(ruta) == 1 else padre,
                    "when": link.when,
                    "default": link.default,
                }
            )
            anidada = _chain_of(link.agent, agent_configs)
            if anidada is not None:
                recorrer(link.agent, anidada, [*ruta, link.agent])

    recorrer(agent_name, raiz, [agent_name])
    return {
        "agent": agent_name,
        "mode": raiz.mode,
        "max_depth": raiz.max_depth,
        "links": links,
    }
