import json
from datetime import datetime

import redis.asyncio as aioredis

from astromesh.core.memory import ConversationBackend, ConversationTurn


class RedisConversationBackend(ConversationBackend):
    def __init__(self, redis_url: str, ttl: int = 3600):
        self._redis = aioredis.from_url(redis_url)
        self._ttl = ttl

    async def save_turn(self, session_id, turn):
        key = f"conv:{session_id}"
        turn_data = json.dumps(
            {
                "role": turn.role,
                "content": turn.content,
                "timestamp": turn.timestamp.isoformat(),
                "metadata": turn.metadata,
                "token_count": turn.token_count,
            }
        )
        await self._redis.rpush(key, turn_data)
        await self._redis.expire(key, self._ttl)

    async def get_history(self, session_id, limit=50):
        raw = await self._redis.lrange(f"conv:{session_id}", -limit, -1)
        turns = []
        for r in raw:
            data = json.loads(r)
            turns.append(
                ConversationTurn(
                    role=data["role"],
                    content=data["content"],
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    metadata=data.get("metadata", {}),
                    token_count=data.get("token_count", 0),
                )
            )
        return turns

    async def clear(self, session_id):
        await self._redis.delete(f"conv:{session_id}")

    async def get_summary(self, session_id):
        result = await self._redis.get(f"conv_summary:{session_id}")
        return result.decode() if result else None

    async def save_summary(self, session_id, summary):
        await self._redis.set(f"conv_summary:{session_id}", summary, ex=self._ttl * 2)
