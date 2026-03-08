import json

import asyncpg

from astromesh.core.memory import ConversationBackend, ConversationTurn


class PGConversationBackend(ConversationBackend):
    def __init__(self, pool: asyncpg.Pool | None = None, dsn: str | None = None):
        self._pool = pool
        self._dsn = dsn

    async def initialize(self):
        if self._pool is None and self._dsn:
            self._pool = await asyncpg.create_pool(self._dsn)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS conversation_history ("
                "id SERIAL PRIMARY KEY, "
                "session_id TEXT, "
                "role TEXT, "
                "content TEXT, "
                "metadata JSONB DEFAULT '{}', "
                "token_count INTEGER DEFAULT 0, "
                "timestamp TIMESTAMPTZ"
                ")"
            )
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS conversation_summaries ("
                "session_id TEXT PRIMARY KEY, "
                "summary TEXT"
                ")"
            )

    async def save_turn(self, session_id, turn):
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO conversation_history "
                "(session_id, role, content, metadata, token_count, timestamp) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                session_id,
                turn.role,
                turn.content,
                json.dumps(turn.metadata),
                turn.token_count,
                turn.timestamp,
            )

    async def get_history(self, session_id, limit=50):
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT role, content, metadata, token_count, timestamp "
                "FROM conversation_history WHERE session_id = $1 "
                "ORDER BY id DESC LIMIT $2",
                session_id,
                limit,
            )
        rows = list(reversed(rows))
        return [
            ConversationTurn(
                role=row["role"],
                content=row["content"],
                timestamp=row["timestamp"],
                metadata=json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"],
                token_count=row["token_count"] or 0,
            )
            for row in rows
        ]

    async def clear(self, session_id):
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM conversation_history WHERE session_id = $1", session_id
            )
            await conn.execute(
                "DELETE FROM conversation_summaries WHERE session_id = $1", session_id
            )

    async def get_summary(self, session_id):
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT summary FROM conversation_summaries WHERE session_id = $1",
                session_id,
            )
        return row["summary"] if row else None

    async def save_summary(self, session_id, summary):
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO conversation_summaries (session_id, summary) "
                "VALUES ($1, $2) "
                "ON CONFLICT (session_id) DO UPDATE SET summary = $2",
                session_id,
                summary,
            )
