import json
import uuid

import asyncpg

from astromesh.core.memory import SemanticBackend, SemanticMemory


class PGVectorSemanticBackend(SemanticBackend):
    def __init__(
        self, pool: asyncpg.Pool | None = None, dsn: str | None = None, dimension: int = 1536
    ):
        self._pool = pool
        self._dsn = dsn
        self._dimension = dimension

    async def initialize(self):
        if self._pool is None and self._dsn:
            self._pool = await asyncpg.create_pool(self._dsn)
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute(
                f"CREATE TABLE IF NOT EXISTS semantic_memories ("
                f"id TEXT PRIMARY KEY, "
                f"agent_id TEXT, "
                f"content TEXT, "
                f"embedding vector({self._dimension}), "
                f"metadata JSONB DEFAULT '{{}}'"
                f")"
            )

    async def store(self, agent_id, content, embedding, metadata):
        memory_id = str(uuid.uuid4())
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO semantic_memories (id, agent_id, content, embedding, metadata) "
                "VALUES ($1, $2, $3, $4, $5)",
                memory_id,
                agent_id,
                content,
                str(embedding),
                json.dumps(metadata),
            )
        return memory_id

    async def search(self, agent_id, query_embedding, top_k=10, threshold=0.7):
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, content, metadata, "
                "1 - (embedding <=> $1::vector) AS similarity "
                "FROM semantic_memories "
                "WHERE agent_id = $2 AND 1 - (embedding <=> $1::vector) >= $3 "
                "ORDER BY similarity DESC LIMIT $4",
                str(query_embedding),
                agent_id,
                threshold,
                top_k,
            )
        return [
            SemanticMemory(
                content=row["content"],
                embedding=[],
                metadata=json.loads(row["metadata"])
                if isinstance(row["metadata"], str)
                else row["metadata"],
                similarity=float(row["similarity"]),
                source=row["id"],
            )
            for row in rows
        ]

    async def delete(self, agent_id, memory_id):
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM semantic_memories WHERE id = $1 AND agent_id = $2",
                memory_id,
                agent_id,
            )
