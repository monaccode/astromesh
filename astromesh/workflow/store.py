from __future__ import annotations

import copy
from abc import ABC, abstractmethod

from astromesh.workflow.models import WorkflowRun


class WorkflowRunStore(ABC):
    @abstractmethod
    async def create(self, run: WorkflowRun) -> None: ...

    @abstractmethod
    async def load(self, run_id: str) -> WorkflowRun | None: ...

    @abstractmethod
    async def save(self, run: WorkflowRun) -> None: ...

    @abstractmethod
    async def list_by_status(self, status: str) -> list[WorkflowRun]: ...


class InMemoryRunStore(WorkflowRunStore):
    """Non-durable store for dev/tests. Deep-copies on the boundary to avoid aliasing."""

    def __init__(self):
        self._runs: dict[str, WorkflowRun] = {}

    async def create(self, run: WorkflowRun) -> None:
        self._runs[run.run_id] = copy.deepcopy(run)

    async def load(self, run_id: str) -> WorkflowRun | None:
        r = self._runs.get(run_id)
        return copy.deepcopy(r) if r is not None else None

    async def save(self, run: WorkflowRun) -> None:
        self._runs[run.run_id] = copy.deepcopy(run)

    async def list_by_status(self, status: str) -> list[WorkflowRun]:
        return [copy.deepcopy(r) for r in self._runs.values() if r.status == status]
