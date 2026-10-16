import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime

from astromesh.core.tokens import estimate_tokens

logger = logging.getLogger(__name__)


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
        # Backends con `initialize()` que todavía no lo corrieron con éxito.
        self._sin_preparar = [b for b in (semantic, episodic) if hasattr(b, "initialize")]
        # Dos primeras corridas concurrentes no pueden inicializar dos veces (pgvector
        # abriría dos pools).
        self._preparando = asyncio.Lock()

    async def _preparar(self):
        """`initialize()` una vez en los backends que lo tienen (pools de Postgres).

        Si falla se loguea y se reintenta en la próxima llamada: la corrida sigue
        sin esa memoria, igual que con un `search`/`store` caído."""
        if not self._sin_preparar:
            return
        async with self._preparando:
            for backend in list(self._sin_preparar):
                try:
                    await backend.initialize()
                except Exception:
                    logger.warning(
                        "memory: initialize() de %s falló para agent=%s; se reintenta",
                        type(backend).__name__,
                        self.agent_id,
                        exc_info=True,
                    )
                    continue
                self._sin_preparar.remove(backend)

    async def build_context(self, session_id, current_query, max_tokens=None):
        """Historial + semántica + episódica. Recorta el historial sólo si se pasa
        `max_tokens`; el engine recorta después con `fit_history`, cuando ya midió
        el system prompt y las tools."""
        context = {"conversation": [], "semantic": [], "episodic": []}
        await self._preparar()

        if self._conversation:
            conv = self.config.get("conversational", {})
            strategy = conv.get("strategy", "sliding_window")
            if strategy == "token_budget":
                turns = await self._conversation.get_history(session_id)
            else:
                turns = await self._conversation.get_history(
                    session_id, limit=conv.get("max_turns", 50)
                )
            # Filas anteriores a este fix tienen token_count=0: se estiman al leer.
            for turn in turns:
                if not turn.token_count:
                    turn.token_count = estimate_tokens(turn.content)
            context["conversation"] = list(turns)
            if strategy == "summary":
                context["conversation_summary"] = await self._conversation.get_summary(session_id)
            if max_tokens is not None:
                self.fit_history(context, max_tokens)

        if self._semantic and self._embed:
            threshold = self.config.get("semantic", {}).get("similarity_threshold", 0.75)
            max_results = self.config.get("semantic", {}).get("max_results", 10)
            try:
                query_emb = await self._embed(current_query)
                encontrados = await self._semantic.search(
                    self.agent_id, query_emb, top_k=max_results, threshold=threshold
                )
                # Sin el vector: al prompt van el texto y de dónde viene.
                context["semantic"] = [
                    {"content": m.content, "similarity": m.similarity, "source": m.source}
                    for m in encontrados
                ]
            except Exception:
                logger.warning(
                    "memory.semantic: la búsqueda falló para agent=%s; sigue sin ella",
                    self.agent_id,
                    exc_info=True,
                )

        if self._episodic:
            try:
                recientes = await self._episodic.recall(self.agent_id, limit=50)
                # Un episodio de otra sesión puede traer la query de otra persona.
                propios = [
                    e for e in recientes if (e.context or {}).get("session_id") == session_id
                ]
                context["episodic"] = [
                    {
                        "event_type": e.event_type,
                        "summary": e.summary,
                        "context": e.context,
                        "outcome": e.outcome,
                        "timestamp": e.timestamp.isoformat(),
                    }
                    for e in propios[:5]
                ]
            except Exception:
                logger.warning(
                    "memory.episodic: recall falló para agent=%s; sigue sin ella",
                    self.agent_id,
                    exc_info=True,
                )

        return context

    async def record_run(
        self,
        session_id: str,
        *,
        query: str | None,
        resultado: str,
        tools: list[str],
        tokens: dict[str, int],
        regla: str | None = None,
    ) -> None:
        """Un episodio por corrida. Nunca levanta; no-op sin backend episódico."""
        if not self._episodic:
            return
        try:
            await self._preparar()
            await self._episodic.record(
                self.agent_id,
                EpisodicMemory(
                    event_type="run",
                    summary=(query or "")[:500],
                    context={"session_id": session_id, "tools": tools},
                    outcome={"result": resultado, "tokens": tokens, "guardrail": regla},
                    timestamp=datetime.now(UTC),
                ),
            )
        except Exception:
            logger.warning(
                "memory.episodic: no se pudo grabar el episodio de agent=%s",
                self.agent_id,
                exc_info=True,
            )

    def fit_history(self, context, budget):
        """Recorta `context["conversation"]` (y el resumen) a `budget` tokens.

        El resumen se cuenta primero; si solo no entra, se descarta. Los turnos
        se eligen de lo más nuevo a lo más viejo con TokenBudgetStrategy.
        `budget=None` no recorta nada: sólo devuelve las cifras (ventana desconocida).
        """
        # Import local: token_budget.py importa ConversationTurn de este módulo.
        from astromesh.memory.strategies.token_budget import TokenBudgetStrategy

        turns = context.get("conversation") or []
        summary = context.get("conversation_summary")
        summary_tokens = estimate_tokens(summary)
        if budget is None:
            return {
                "turns_kept": len(turns),
                "turns_dropped": 0,
                "tokens": summary_tokens + sum(t.token_count for t in turns),
                "summary_used": bool(summary),
            }
        if summary_tokens > budget:
            context["conversation_summary"] = summary = None
            summary_tokens = 0
        kept = TokenBudgetStrategy().apply(turns, budget=max(0, budget - summary_tokens))
        context["conversation"] = kept
        return {
            "turns_kept": len(kept),
            "turns_dropped": len(turns) - len(kept),
            "tokens": summary_tokens + sum(t.token_count for t in kept),
            "summary_used": bool(summary),
        }

    async def clear_history(self, session_id):
        if self._conversation:
            await self._conversation.clear(session_id)

    async def persist_turn(self, session_id, turn):
        await self._preparar()
        # Antes del `if`: la escritura semántica de abajo lo usa, haya o no conversacional.
        if not turn.token_count:
            turn.token_count = estimate_tokens(turn.content)
        if self._conversation:
            await self._conversation.save_turn(session_id, turn)
            max_turns = self.config.get("conversational", {}).get("max_turns", 50)
            # Resumen incremental, una vez por intercambio (tras el assistant): se
            # resumen los turnos que acaban de salir de la ventana verbatim
            # (`build_context` trae los últimos `max_turns`) junto al resumen anterior.
            if turn.role == "assistant" and self._summarize:
                history = await self._conversation.get_history(session_id, limit=max_turns + 2)
                if len(history) > max_turns:
                    try:
                        previous = await self._conversation.get_summary(session_id)
                        summary = await self._summarize(history[:-max_turns], previous)
                        await self._conversation.save_summary(session_id, summary)
                    except Exception:
                        logger.warning(
                            "memory.summary falló para agent=%s session=%s; "
                            "queda el resumen anterior",
                            self.agent_id,
                            session_id,
                            exc_info=True,
                        )

        if self._semantic and self._embed and turn.role == "assistant" and turn.token_count > 50:
            try:
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
            except Exception:
                logger.warning(
                    "memory.semantic: store falló para agent=%s session=%s; el turno "
                    "no queda en la memoria semántica",
                    self.agent_id,
                    session_id,
                    exc_info=True,
                )
