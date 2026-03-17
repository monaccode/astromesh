from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ConversationTurn:
    role: str
    content: str
    timestamp: datetime
    metadata: dict = field(default_factory=dict)
    token_count: int = 0


@dataclass
class SemanticMemory:
    content: str
    embedding: list[float]
    metadata: dict
    similarity: float = 0.0
    source: str = ""


@dataclass
class EpisodicMemory:
    event_type: str
    summary: str
    context: dict
    outcome: dict
    timestamp: datetime
    importance_score: float = 0.5


class ConversationBackend(ABC):
    @abstractmethod
    async def save_turn(self, session_id, turn): ...

    @abstractmethod
    async def get_history(self, session_id, limit=50) -> list[ConversationTurn]: ...

    @abstractmethod
    async def clear(self, session_id): ...

    @abstractmethod
    async def get_summary(self, session_id) -> str | None: ...

    @abstractmethod
    async def save_summary(self, session_id, summary): ...


class SemanticBackend(ABC):
    @abstractmethod
    async def store(self, agent_id, content, embedding, metadata): ...

    @abstractmethod
    async def search(
        self, agent_id, query_embedding, top_k=10, threshold=0.7
    ) -> list[SemanticMemory]: ...

    @abstractmethod
    async def delete(self, agent_id, memory_id): ...


class EpisodicBackend(ABC):
    @abstractmethod
    async def record(self, agent_id, episode): ...

    @abstractmethod
    async def recall(
        self, agent_id, event_type=None, since=None, limit=20
    ) -> list[EpisodicMemory]: ...


class MemoryManager:
    def __init__(
        self,
        agent_id,
        config,
        conversation=None,
        semantic=None,
        episodic=None,
        embedding_fn=None,
        summarize_fn=None,
    ):
        self.agent_id = agent_id
        self.config = config
        self._conversation = conversation
        self._semantic = semantic
        self._episodic = episodic
        self._embed = embedding_fn
        self._summarize = summarize_fn

    async def build_context(self, session_id, current_query, max_tokens=4096):
        context = {"conversation": [], "semantic": [], "episodic": []}
        token_budget = max_tokens

        if self._conversation:
            strategy = self.config.get("conversational", {}).get("strategy", "sliding_window")
            if strategy == "sliding_window":
                turns = await self._conversation.get_history(session_id)
                context["conversation"] = turns
                token_budget -= sum(t.token_count for t in turns)
            elif strategy == "summary":
                summary = await self._conversation.get_summary(session_id)
                recent = await self._conversation.get_history(session_id, limit=5)
                context["conversation_summary"] = summary
                context["conversation"] = recent
            elif strategy == "token_budget":
                turns = await self._conversation.get_history(session_id)
                selected, used = [], 0
                for turn in reversed(turns):
                    if used + turn.token_count > token_budget * 0.5:
                        break
                    selected.insert(0, turn)
                    used += turn.token_count
                context["conversation"] = selected
                token_budget -= used

        if self._semantic and self._embed:
            query_emb = await self._embed(current_query)
            threshold = self.config.get("semantic", {}).get("similarity_threshold", 0.75)
            max_results = self.config.get("semantic", {}).get("max_results", 10)
            context["semantic"] = await self._semantic.search(
                self.agent_id, query_emb, top_k=max_results, threshold=threshold
            )

        if self._episodic:
            context["episodic"] = await self._episodic.recall(self.agent_id, limit=5)

        return context

    async def clear_history(self, session_id):
        if self._conversation:
            await self._conversation.clear(session_id)

    async def persist_turn(self, session_id, turn):
        if self._conversation:
            await self._conversation.save_turn(session_id, turn)
            history = await self._conversation.get_history(session_id)
            max_turns = self.config.get("conversational", {}).get("max_turns", 50)
            if len(history) > max_turns and self._summarize:
                summary = await self._summarize(history[:-10])
                await self._conversation.save_summary(session_id, summary)

        if self._semantic and self._embed and turn.role == "assistant" and turn.token_count > 50:
            emb = await self._embed(turn.content)
            await self._semantic.store(
                self.agent_id,
                turn.content,
                emb,
                {
                    "session_id": session_id,
                    "timestamp": turn.timestamp.isoformat(),
                },
            )
