from fastapi import APIRouter, HTTPException, Query

from astromesh.observability.collector import Collector, InternalCollector

router = APIRouter(prefix="/traces", tags=["observability"])
_collector: Collector = InternalCollector()


def set_collector(collector: Collector) -> None:
    global _collector
    _collector = collector


def get_collector() -> Collector:
    return _collector


@router.get("/")
async def list_traces(
    agent: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    traces = await _collector.query_traces(agent=agent, limit=limit)
    return {"traces": traces}


@router.get("/{trace_id}")
async def get_trace(trace_id: str):
    trace = await _collector.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace
