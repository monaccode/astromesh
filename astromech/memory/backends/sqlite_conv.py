import json
from datetime import datetime

import aiosqlite

from astromech.core.memory import ConversationBackend, ConversationTurn


class SQLiteConversationBackend(ConversationBackend):
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self):
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS conversations ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "session_id TEXT, "
            "role TEXT, "
            "content TEXT, "
            "metadata TEXT, "
            "token_count INTEGER, "
            "timestamp TEXT"
            ")"
        )
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS summaries ("
            "session_id TEXT PRIMARY KEY, "
            "summary TEXT"
            ")"
        )
        await self._db.commit()

    async def save_turn(self, session_id, turn):
        await self._db.execute(
            "INSERT INTO conversations (session_id, role, content, metadata, token_count, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                turn.role,
                turn.content,
                json.dumps(turn.metadata),
                turn.token_count,
                turn.timestamp.isoformat(),
            ),
        )
        await self._db.commit()

    async def get_history(self, session_id, limit=50):
        cursor = await self._db.execute(
            "SELECT role, content, metadata, token_count, timestamp "
            "FROM conversations WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        )
        rows = await cursor.fetchall()
        rows.reverse()
        return [
            ConversationTurn(
                role=row[0],
                content=row[1],
                timestamp=datetime.fromisoformat(row[4]),
                metadata=json.loads(row[2]) if row[2] else {},
                token_count=row[3] or 0,
            )
            for row in rows
        ]

    async def clear(self, session_id):
        await self._db.execute(
            "DELETE FROM conversations WHERE session_id = ?", (session_id,)
        )
        await self._db.execute(
            "DELETE FROM summaries WHERE session_id = ?", (session_id,)
        )
        await self._db.commit()

    async def get_summary(self, session_id):
        cursor = await self._db.execute(
            "SELECT summary FROM summaries WHERE session_id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def save_summary(self, session_id, summary):
        await self._db.execute(
            "INSERT OR REPLACE INTO summaries (session_id, summary) VALUES (?, ?)",
            (session_id, summary),
        )
        await self._db.commit()
