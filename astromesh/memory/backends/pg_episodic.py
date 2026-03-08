import json

import asyncpg

from astromesh.core.memory import EpisodicBackend, EpisodicMemory


class PGEpisodicBackend(EpisodicBackend):
    def __init__(self, pool: asyncpg.Pool | None = None, dsn: str | None = None):
        self._pool = pool
        self._dsn = dsn

    async def initialize(self):
        if self._pool is None and self._dsn:
            self._pool = await asyncpg.create_pool(self._dsn)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS episodic_memories ("
                "id SERIAL PRIMARY KEY, "
                "agent_id TEXT, "
                "event_type TEXT, "
                "summary TEXT, "
                "context JSONB DEFAULT '{}', "
                "outcome JSONB DEFAULT '{}', "
                "importance_score FLOAT DEFAULT 0.5, "
                "timestamp TIMESTAMPTZ"
                ")"
            )

    async def record(self, agent_id, episode):
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO episodic_memories "
                "(agent_id, event_type, summary, context, outcome, importance_score, timestamp) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                agent_id,
                episode.event_type,
                episode.summary,
                json.dumps(episode.context),
                json.dumps(episode.outcome),
                episode.importance_score,
                episode.timestamp,
            )

    async def recall(self, agent_id, event_type=None, since=None, limit=20):
        query = "SELECT event_type, summary, context, outcome, importance_score, timestamp FROM episodic_memories WHERE agent_id = $1"
        params: list = [agent_id]
        idx = 2

        if event_type is not None:
            query += f" AND event_type = ${idx}"
            params.append(event_type)
            idx += 1

        if since is not None:
            query += f" AND timestamp >= ${idx}"
            params.append(since)
            idx += 1

        query += f" ORDER BY timestamp DESC LIMIT ${idx}"
        params.append(limit)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [
            EpisodicMemory(
                event_type=row["event_type"],
                summary=row["summary"],
                context=json.loads(row["context"]) if isinstance(row["context"], str) else row["context"],
                outcome=json.loads(row["outcome"]) if isinstance(row["outcome"], str) else row["outcome"],
                importance_score=row["importance_score"],
                timestamp=row["timestamp"],
            )
            for row in rows
        ]
