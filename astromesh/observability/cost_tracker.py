import os
from dataclasses import dataclass, field
from datetime import datetime

try:
    from astromesh._native import RustCostIndex
    _HAS_NATIVE_COST = True
except ImportError:
    _HAS_NATIVE_COST = False


@dataclass
class UsageRecord:
    agent_name: str
    session_id: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    pattern: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


class CostTracker:
    """Track costs per agent, session, and model."""

    def __init__(self):
        self._records: list[UsageRecord] = []
        self._budgets: dict[str, float] = {}  # agent_name -> max_usd
        self._native_index = RustCostIndex() if _HAS_NATIVE_COST else None

    def record(self, record: UsageRecord):
        self._records.append(record)
        if self._native_index is not None and not os.environ.get("ASTROMESH_FORCE_PYTHON"):
            self._native_index.record(
                record.agent_name, record.session_id, record.model, record.provider,
                record.cost_usd, record.latency_ms, record.input_tokens, record.output_tokens,
                record.timestamp.timestamp(),
            )

    def set_budget(self, agent_name: str, max_usd: float):
        self._budgets[agent_name] = max_usd

    def check_budget(self, agent_name: str) -> dict:
        budget = self._budgets.get(agent_name)
        spent = self.get_total_cost(agent_name=agent_name)
        if budget is None:
            return {"has_budget": False, "spent": spent}
        return {
            "has_budget": True,
            "budget": budget,
            "spent": spent,
            "remaining": budget - spent,
            "exceeded": spent >= budget,
        }

    def get_total_cost(self, agent_name: str | None = None,
                       session_id: str | None = None,
                       since: datetime | None = None) -> float:
        if self._native_index is not None and not os.environ.get("ASTROMESH_FORCE_PYTHON"):
            return self._native_index.total_cost(
                agent_name, session_id,
                since.timestamp() if since else None,
            )
        records = self._records
        if agent_name:
            records = [r for r in records if r.agent_name == agent_name]
        if session_id:
            records = [r for r in records if r.session_id == session_id]
        if since:
            records = [r for r in records if r.timestamp >= since]
        return sum(r.cost_usd for r in records)

    def get_usage_summary(self, agent_name: str | None = None) -> dict:
        records = self._records
        if agent_name:
            records = [r for r in records if r.agent_name == agent_name]

        if not records:
            return {"total_cost": 0.0, "total_tokens": 0, "num_calls": 0}

        return {
            "total_cost": sum(r.cost_usd for r in records),
            "total_input_tokens": sum(r.input_tokens for r in records),
            "total_output_tokens": sum(r.output_tokens for r in records),
            "total_tokens": sum(r.input_tokens + r.output_tokens for r in records),
            "num_calls": len(records),
            "avg_latency_ms": sum(r.latency_ms for r in records) / len(records),
            "by_provider": self._group_by(records, "provider"),
            "by_model": self._group_by(records, "model"),
        }

    def _group_by(self, records: list[UsageRecord], field: str) -> dict:
        groups: dict[str, dict] = {}
        for r in records:
            key = getattr(r, field)
            if key not in groups:
                groups[key] = {"cost": 0.0, "calls": 0, "tokens": 0}
            groups[key]["cost"] += r.cost_usd
            groups[key]["calls"] += 1
            groups[key]["tokens"] += r.input_tokens + r.output_tokens
        return groups
