from fastapi import APIRouter

router = APIRouter(prefix="/metrics", tags=["observability"])

# In-memory counters (simple approach, later backed by prometheus-client)
_counters: dict[str, int] = {}
_histograms: dict[str, list[float]] = {}


def increment(name: str, value: int = 1):
    _counters[name] = _counters.get(name, 0) + value


def observe(name: str, value: float):
    _histograms.setdefault(name, []).append(value)


def get_counters() -> dict[str, int]:
    return dict(_counters)


def get_histograms() -> dict[str, dict]:
    result = {}
    for name, values in _histograms.items():
        if values:
            result[name] = {
                "count": len(values),
                "sum": sum(values),
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
            }
    return result


@router.get("/")
async def get_metrics():
    return {"counters": get_counters(), "histograms": get_histograms()}


@router.post("/reset")
async def reset_metrics():
    _counters.clear()
    _histograms.clear()
    return {"status": "reset"}
