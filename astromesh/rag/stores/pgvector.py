from __future__ import annotations

import json

from astromesh.rag.stores.base import VectorStore


class PGVectorStore(VectorStore):
    """Vector store backed by PostgreSQL with pgvector extension."""

    def __init__(
        self,
        dsn: str = "postgresql://localhost:5432/astromesh",
        table: str = "embeddings",
        dimensions: int = 384,
    ):
        self.dsn = dsn
        self.table = table
        self.dimensions = dimensions
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg

            self._pool = await asyncpg.create_pool(self.dsn)
            async with self._pool.acquire() as conn:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.table} (
                        doc_id TEXT PRIMARY KEY,
                        embedding vector({self.dimensions}),
                        content TEXT NOT NULL,
                        metadata JSONB DEFAULT '{{}}'::jsonb
                    )
                """)
        return self._pool

    async def upsert(self, doc_id: str, embedding: list[float], content: str, metadata: dict):
        pool = await self._get_pool()
        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {self.table} (doc_id, embedding, content, metadata)
                VALUES ($1, $2::vector, $3, $4::jsonb)
                ON CONFLICT (doc_id)
                DO UPDATE SET embedding = EXCLUDED.embedding,
                              content = EXCLUDED.content,
                              metadata = EXCLUDED.metadata
                """,
                doc_id,
                vec_str,
                content,
                json.dumps(metadata),
            )

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[dict]:
        pool = await self._get_pool()
        vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        where_clause = ""
        if filters:
            conditions = []
            for key, value in filters.items():
                conditions.append(f"metadata->>'{key}' = '{value}'")
            where_clause = "WHERE " + " AND ".join(conditions)

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT doc_id, content, metadata,
                       1 - (embedding <=> $1::vector) AS score
                FROM {self.table}
                {where_clause}
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                vec_str,
                top_k,
            )

        return [
            {
                "doc_id": row["doc_id"],
                "content": row["content"],
                "metadata": json.loads(row["metadata"]),
                "score": float(row["score"]),
            }
            for row in rows
        ]

    async def delete(self, doc_id: str):
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"DELETE FROM {self.table} WHERE doc_id = $1", doc_id)

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None
