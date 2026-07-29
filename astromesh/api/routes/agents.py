import copy
import logging
from dataclasses import asdict, is_dataclass

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from astromesh.api.usage import usage_from_trace
from astromesh.errors import ModelProviderError, model_provider_error_payload


def _steps_to_dicts(steps: list | None) -> list[dict]:
    """Orchestration returns AgentStep dataclasses; OpenAPI expects JSON objects."""
    if not steps:
        return []
    out: list[dict] = []
    for item in steps:
        if isinstance(item, dict):
            out.append(item)
        elif is_dataclass(item):
            out.append(asdict(item))
        else:
            out.append({"result": str(item)})
    return out


router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory storage (will be replaced by runtime in production)
_runtime = None


def set_runtime(runtime):
    global _runtime
    _runtime = runtime


class AgentRunRequest(BaseModel):
    query: str
    session_id: str = "default"
    context: dict | None = None
    connections: dict | None = None
    """Credenciales resueltas por corrida, inyectadas por el plano de control.

    No se persisten: no entran a la traza, ni a la memoria, ni a la respuesta.
    """


class ModelUsage(BaseModel):
    """Consumo atribuido a un modelo dentro de una corrida.

    Una invocación toca habitualmente varios modelos: por el patrón de
    orquestación, por el enrutamiento por rol, o por fallback entre proveedores.
    """

    provider: str = ""
    model: str = ""
    role: str = "default"
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0


class UsageInfo(BaseModel):
    tokens_in: int = 0
    tokens_out: int = 0
    # Primer modelo visto. Sin valor correcto posible en una corrida multi-modelo;
    # se conserva por compatibilidad. Usar by_model para atribuir consumo.
    model: str = ""
    by_model: list[ModelUsage] = []


class AgentRunResponse(BaseModel):
    answer: str
    steps: list[dict] = []
    usage: UsageInfo | None = None
    trace: dict | None = None
    data: dict | None = None
    chain: dict | None = None


@router.get("/agents")
async def list_agents():
    if _runtime:
        return {"agents": _runtime.list_agents()}
    return {"agents": []}


@router.get("/agents/{agent_name}")
async def get_agent(agent_name: str):
    if not _runtime:
        raise HTTPException(status_code=404, detail="Runtime not initialized")
    config = _runtime._agent_configs.get(agent_name)
    if config is not None:
        return copy.deepcopy(config)
    agent = _runtime._agents.get(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {
            "name": agent.name,
            "version": agent.version,
            "namespace": agent.namespace,
        },
        "spec": {
            "identity": {
                "display_name": agent.name,
                "description": agent.description or "",
            },
            "model": {
                "primary": {
                    "provider": "ollama",
                    "model": "llama3.1:8b",
                    "endpoint": "http://127.0.0.1:11434",
                },
                "routing": {"strategy": "cost_optimized"},
            },
            "prompts": {"system": ""},
            "orchestration": {"pattern": "react", "max_iterations": 10},
        },
    }


@router.post("/agents", status_code=201)
async def create_agent(config: dict):
    """Register a new agent dynamically."""
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    try:
        await _runtime.register_agent(config)
        name = config.get("metadata", {}).get("name") or config.get("spec", {}).get(
            "identity", {}
        ).get("name", "unknown")
        return {"name": name, "status": "registered"}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/agents/{agent_name}")
async def delete_agent(agent_name: str):
    """Remove a dynamically registered agent."""
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    try:
        _runtime.unregister_agent(agent_name)
        return {"name": agent_name, "status": "removed"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/agents/{agent_name}")
async def update_agent(agent_name: str, config: dict):
    """Update an existing agent's configuration."""
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    try:
        await _runtime.update_agent(agent_name, config)
        return {"agent": agent_name, "status": "updated"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/agents/{agent_name}/deploy")
async def deploy_agent(agent_name: str):
    """Deploy a draft/paused agent to the runtime."""
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    try:
        await _runtime.deploy_agent(agent_name)
        return {"agent": agent_name, "status": "deployed"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/agents/{agent_name}/pause")
async def pause_agent(agent_name: str):
    """Pause a deployed agent."""
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    try:
        _runtime.pause_agent(agent_name)
        return {"agent": agent_name, "status": "paused"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


def _link_desde_step(agent_name: str, step_result) -> dict:
    """Traduce un StepResult de la cadena al link que ve el cliente."""
    from astromesh.workflow.models import StepStatus

    if step_result.status == StepStatus.SKIPPED:
        return {"agent": agent_name, "status": "skipped", "reason": "condition_false"}
    if step_result.status == StepStatus.ERROR:
        return {"agent": agent_name, "status": "error", "error": step_result.error}

    salida = step_result.output if isinstance(step_result.output, dict) else {}
    link = {"agent": agent_name, "status": "success", "answer": salida.get("answer", "")}
    if salida.get("data") is not None:
        link["data"] = salida["data"]
    if step_result.duration_ms is not None:
        link["duration_ms"] = step_result.duration_ms
    return link


def _construir_chain(wf_result, agent_name: str, grafo: dict) -> dict:
    """Arma el bloque `chain` a partir del resultado del workflow compilado."""
    links = []
    hubo_error = False
    for entrada in grafo["links"]:
        # El compilador nombra cada paso `<padre>__<hijo>`.
        padre = entrada["via"] or agent_name
        step = wf_result.steps.get(f"{padre}__{entrada['agent']}")
        if step is None:
            # El eslabón nunca llegó a evaluarse: alguien antes cortó la corrida.
            link = {"agent": entrada["agent"], "status": "skipped", "reason": "upstream_stopped"}
        else:
            link = _link_desde_step(entrada["agent"], step)
            hubo_error = hubo_error or link["status"] == "error"
        link["depth"] = entrada["depth"]
        link["via"] = entrada["via"]
        links.append(link)

    if wf_result.status == "failed":
        status = "failed"
    elif hubo_error:
        status = "partial"
    else:
        status = "completed"

    return {
        "run_id": wf_result.run_id,
        "status": status,
        "mode": grafo["mode"],
        "links": links,
    }


@router.post("/agents/{agent_name}/run")
async def run_agent(agent_name: str, request: AgentRunRequest, http_request: Request):
    if not _runtime:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    try:
        context = dict(request.context) if request.context else {}

        provider_key = http_request.headers.get("X-Astromesh-Provider-Key")
        provider_name = http_request.headers.get("X-Astromesh-Provider-Name")
        if provider_key and provider_name:
            context["_provider_override"] = {"name": provider_name, "key": provider_key}

        logger.debug(
            "run_agent start agent=%s session=%s query_chars=%d",
            agent_name,
            request.session_id,
            len(request.query),
        )
        engine = getattr(http_request.app.state, "workflow_engine", None)
        tiene_cadena = getattr(_runtime, "has_chain", lambda _: False)(agent_name)

        if tiene_cadena and engine is not None:
            from astromesh.chain.compiler import chain_graph, chain_workflow_name

            wf_result = await engine.run(
                chain_workflow_name(agent_name),
                trigger={
                    "query": request.query,
                    "session_id": request.session_id,
                    "context": context,
                },
            )
            paso_a = wf_result.steps.get(agent_name)
            result = paso_a.output if paso_a and isinstance(paso_a.output, dict) else {}
            grafo = chain_graph(agent_name, _runtime.agent_configs)
            chain_block = _construir_chain(wf_result, agent_name, grafo)
        else:
            result = await _runtime.run(
                agent_name,
                request.query,
                request.session_id,
                context,
                connections=request.connections,
            )
            chain_block = None

        logger.debug(
            "run_agent done agent=%s session=%s answer_chars=%d steps=%d cadena=%s",
            agent_name,
            request.session_id,
            len(result.get("answer", "") or ""),
            len(result.get("steps") or []),
            bool(chain_block),
        )
        trace = result.get("trace", {})
        usage_data = usage_from_trace(trace)
        usage = UsageInfo(**usage_data) if usage_data else None
        return AgentRunResponse(
            answer=result.get("answer", ""),
            steps=_steps_to_dicts(result.get("steps")),
            usage=usage,
            trace=trace or None,
            data=result.get("data"),
            chain=chain_block,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ModelProviderError as e:
        raise HTTPException(status_code=502, detail=model_provider_error_payload(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/agents/{agent_name}/chain")
async def get_agent_chain(agent_name: str):
    """El grafo de la cadena, ya expandido. Es un artefacto de compilación:
    se puede pedir sin ejecutar nada."""
    if not _runtime:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    if agent_name not in _runtime.agent_configs:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    from astromesh.chain.compiler import chain_graph

    grafo = chain_graph(agent_name, _runtime.agent_configs)
    if grafo is None:
        raise HTTPException(
            status_code=404, detail=f"Agent '{agent_name}' does not declare spec.chain"
        )
    return grafo
