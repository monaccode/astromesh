import pytest
from datetime import datetime
from unittest.mock import AsyncMock

from astromech.core.memory import (
    ConversationTurn,
    SemanticMemory,
    EpisodicMemory,
    MemoryManager,
)


def test_conversation_turn():
    turn = ConversationTurn(
        role="user", content="Hello", timestamp=datetime(2026, 1, 1)
    )
    assert turn.role == "user"
    assert turn.content == "Hello"
    assert turn.metadata == {}
    assert turn.token_count == 0


def test_semantic_memory():
    mem = SemanticMemory(
        content="Some fact", embedding=[0.1, 0.2], metadata={"source": "doc"}
    )
    assert mem.content == "Some fact"
    assert mem.embedding == [0.1, 0.2]
    assert mem.similarity == 0.0
    assert mem.source == ""


def test_episodic_memory():
    ep = EpisodicMemory(
        event_type="tool_call",
        summary="Called search",
        context={"query": "test"},
        outcome={"status": "ok"},
        timestamp=datetime(2026, 1, 1),
    )
    assert ep.event_type == "tool_call"
    assert ep.importance_score == 0.5


@pytest.mark.asyncio
async def test_memory_manager_build_context():
    """MemoryManager.build_context with sliding_window strategy."""
    turns = [
        ConversationTurn(
            role="user",
            content="Hi",
            timestamp=datetime(2026, 1, 1),
            token_count=5,
        ),
        ConversationTurn(
            role="assistant",
            content="Hello!",
            timestamp=datetime(2026, 1, 1),
            token_count=8,
        ),
    ]

    conversation = AsyncMock()
    conversation.get_history = AsyncMock(return_value=turns)

    config = {"conversational": {"strategy": "sliding_window"}}
    manager = MemoryManager(
        agent_id="agent-1", config=config, conversation=conversation
    )

    context = await manager.build_context(session_id="sess-1", current_query="test")

    assert context["conversation"] == turns
    conversation.get_history.assert_called_once_with("sess-1")


@pytest.mark.asyncio
async def test_memory_manager_persist_turn():
    """MemoryManager.persist_turn saves turn and checks history length."""
    turn = ConversationTurn(
        role="user", content="Hi", timestamp=datetime(2026, 1, 1), token_count=5
    )

    conversation = AsyncMock()
    conversation.save_turn = AsyncMock()
    conversation.get_history = AsyncMock(return_value=[turn])

    config = {"conversational": {"max_turns": 50}}
    manager = MemoryManager(
        agent_id="agent-1", config=config, conversation=conversation
    )

    await manager.persist_turn(session_id="sess-1", turn=turn)

    conversation.save_turn.assert_called_once_with("sess-1", turn)
    conversation.get_history.assert_called_once_with("sess-1")
