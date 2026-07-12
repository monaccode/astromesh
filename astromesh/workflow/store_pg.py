from __future__ import annotations

import json

import asyncpg

from astromesh.workflow.models import WorkflowRun
from astromesh.workflow.store import WorkflowRunStore

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


class PgRunStore(WorkflowRunStore):
    """Durable store respaldado por Postgres, vía asyncpg. Espeja SqliteRunStore."""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS workflow_runs ("
                "run_id TEXT PRIMARY KEY, workflow_name TEXT, status TEXT, current_index INTEGER, "
                "context TEXT, resume_key TEXT, created_at TEXT, updated_at TEXT, "
                "expires_at TEXT, error TEXT, pending_approval TEXT)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS workflow_runs_status_idx ON workflow_runs (status)"
            )

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
        cols = ", ".join(_COLS)
        placeholders = ", ".join(f"${i + 1}" for i in range(len(_COLS)))
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLS if c != "run_id")
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO workflow_runs ({cols}) VALUES ({placeholders}) "
                f"ON CONFLICT (run_id) DO UPDATE SET {updates}",
                *self._row(run),
            )

    async def load(self, run_id: str) -> WorkflowRun | None:
        cols = ", ".join(_COLS)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT {cols} FROM workflow_runs WHERE run_id = $1", run_id)
        return self._from_row(row) if row else None

    async def list_by_status(self, status: str) -> list[WorkflowRun]:
        cols = ", ".join(_COLS)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(f"SELECT {cols} FROM workflow_runs WHERE status = $1", status)
        return [self._from_row(r) for r in rows]
