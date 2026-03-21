import copy

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()

# In-memory storage (will be replaced by runtime in production)
_runtime = None


def set_runtime(runtime):
    global _runtime
    _runtime = runtime


class AgentRunRequest(BaseModel):
    query: str
    session_id: str = "default"
    context: dict | None = None


class UsageInfo(BaseModel):
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""


class AgentRunResponse(BaseModel):
    answer: str
    steps: list[dict] = []
    usage: UsageInfo | None = None
    trace: dict | None = None


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
        name = config.get("metadata", {}).get("name") or config.get("spec", {}).get("identity", {}).get("name", "unknown")
        return {"name": name, "status": "registered"}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agents/{agent_name}")
async def delete_agent(agent_name: str):
    """Remove a dynamically registered agent."""
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    try:
        _runtime.unregister_agent(agent_name)
        return {"name": agent_name, "status": "removed"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/agents/{agent_name}")
async def update_agent(agent_name: str, config: dict):
    """Update an existing agent's configuration."""
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    try:
        await _runtime.update_agent(agent_name, config)
        return {"agent": agent_name, "status": "updated"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/agents/{agent_name}/deploy")
async def deploy_agent(agent_name: str):
    """Deploy a draft/paused agent to the runtime."""
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    try:
        await _runtime.deploy_agent(agent_name)
        return {"agent": agent_name, "status": "deployed"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/agents/{agent_name}/pause")
async def pause_agent(agent_name: str):
    """Pause a deployed agent."""
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    try:
        _runtime.pause_agent(agent_name)
        return {"agent": agent_name, "status": "paused"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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

        result = await _runtime.run(agent_name, request.query, request.session_id, context)
        usage = None
        trace = result.get("trace", {})
        spans = trace.get("spans", []) if isinstance(trace, dict) else []
        total_in = 0
        total_out = 0
        model_used = ""
        for span in spans:
            span_meta = span.get("metadata", {})
            if "usage" in span_meta:
                u = span_meta["usage"]
                total_in += u.get("prompt_tokens", 0)
                total_out += u.get("completion_tokens", 0)
            if "model" in span_meta and not model_used:
                model_used = span_meta["model"]
        if total_in or total_out:
            usage = UsageInfo(tokens_in=total_in, tokens_out=total_out, model=model_used)
        return AgentRunResponse(answer=result.get("answer", ""), steps=result.get("steps", []), usage=usage, trace=trace if trace else None)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
