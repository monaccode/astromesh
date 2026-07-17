from __future__ import annotations

import copy
import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from astromesh.workflow.models import WorkflowRun

if TYPE_CHECKING:
    import aiosqlite


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


class SqliteRunStore(WorkflowRunStore):
    """Durable store backed by SQLite, via aiosqlite."""

    _COLS = (
        "run_id",
        "workflow_name",
        "status",
        "current_index",
        "context",
        "resume_key",
        "created_at",
        "updated_at",
        "expires_at",
        "error",
        "pending_approval",
    )

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        import aiosqlite

        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS workflow_runs ("
            "run_id TEXT PRIMARY KEY, workflow_name TEXT, status TEXT, current_index INTEGER, "
            "context TEXT, resume_key TEXT, created_at TEXT, updated_at TEXT, "
            "expires_at TEXT, error TEXT, pending_approval TEXT)"
        )
        # Idempotent migration: a table created by the earlier async-durable
        # slice (10 cols, no pending_approval) is a no-op for CREATE TABLE IF
        # NOT EXISTS above, so backfill the column here if it's missing.
        cur = await self._db.execute("PRAGMA table_info(workflow_runs)")
        existing = {row[1] for row in await cur.fetchall()}
        if "pending_approval" not in existing:
            await self._db.execute("ALTER TABLE workflow_runs ADD COLUMN pending_approval TEXT")
        await self._db.commit()

    def _row(self, run: WorkflowRun) -> tuple:
        return (
            run.run_id,
            run.workflow_name,
            run.status,
            run.current_index,
            json.dumps(run.context),
            run.resume_key,
            run.created_at,
            run.updated_at,
            run.expires_at,
            run.error,
            json.dumps(run.pending_approval),
        )

    def _from_row(self, row) -> WorkflowRun:
        return WorkflowRun(
            run_id=row[0],
            workflow_name=row[1],
            status=row[2],
            current_index=row[3],
            context=json.loads(row[4]) if row[4] else {},
            resume_key=row[5],
            created_at=row[6],
            updated_at=row[7],
            expires_at=row[8],
            error=row[9],
            pending_approval=json.loads(row[10]) if row[10] else None,
        )

    async def create(self, run: WorkflowRun) -> None:
        await self.save(run)

    async def save(self, run: WorkflowRun) -> None:
        placeholders = ", ".join("?" for _ in self._COLS)
        await self._db.execute(
            f"INSERT OR REPLACE INTO workflow_runs ({', '.join(self._COLS)}) "
            f"VALUES ({placeholders})",
            self._row(run),
        )
        await self._db.commit()

    async def load(self, run_id: str) -> WorkflowRun | None:
        cur = await self._db.execute(
            f"SELECT {', '.join(self._COLS)} FROM workflow_runs WHERE run_id = ?", (run_id,)
        )
        row = await cur.fetchone()
        return self._from_row(row) if row else None

    async def list_by_status(self, status: str) -> list[WorkflowRun]:
        cur = await self._db.execute(
            f"SELECT {', '.join(self._COLS)} FROM workflow_runs WHERE status = ?", (status,)
        )
        return [self._from_row(r) for r in await cur.fetchall()]
