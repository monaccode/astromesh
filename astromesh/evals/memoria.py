"""Backend conversacional en memoria: un eval nunca escribe en Redis ni Postgres."""

from __future__ import annotations

from collections import defaultdict

from astromesh.core.memory import ConversationBackend


class MemoriaDeEval(ConversationBackend):
    def __init__(self):
        self._turnos: dict[str, list] = defaultdict(list)
        self._resumenes: dict[str, str] = {}

    async def save_turn(self, session_id, turn):
        self._turnos[session_id].append(turn)

    async def get_history(self, session_id, limit=50):
        return list(self._turnos.get(session_id, [])[-limit:])

    async def clear(self, session_id):
        self._turnos.pop(session_id, None)
        self._resumenes.pop(session_id, None)

    async def get_summary(self, session_id):
        return self._resumenes.get(session_id)

    async def save_summary(self, session_id, summary):
        self._resumenes[session_id] = summary
