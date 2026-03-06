import sys
import json
import types
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from astromech.core.memory import ConversationTurn


# ---------------------------------------------------------------------------
# Helpers: inject fake third-party modules so backends can be imported
# without the real packages installed.
# ---------------------------------------------------------------------------

def _ensure_fake_module(name, attrs=None):
    """Insert a fake module into sys.modules if not already present."""
    if name not in sys.modules:
        mod = types.ModuleType(name)
        if attrs:
            for k, v in attrs.items():
                setattr(mod, k, v)
        sys.modules[name] = mod
    return sys.modules[name]


# -- fake redis.asyncio ---
_fake_redis = _ensure_fake_module("redis")
_fake_aioredis = _ensure_fake_module("redis.asyncio")
_fake_aioredis.from_url = MagicMock()

# -- fake aiosqlite (needs to be a real working async context manager for SQLite tests) ---
# We'll handle aiosqlite separately per-test since we want a real in-memory backend.
# For now just ensure the module entry exists so the import doesn't fail at collection time.
# We'll use a dedicated fixture.

# -- fake asyncpg ---
_fake_asyncpg = _ensure_fake_module("asyncpg")
_fake_asyncpg.Pool = type("Pool", (), {})
_fake_asyncpg.create_pool = AsyncMock()

# numpy and faiss are NOT faked at module level; tests skip if not installed.


# ===================== Redis conversation backend tests =====================

@pytest.mark.asyncio
async def test_redis_conv_save_and_get():
    mock_redis = AsyncMock()
    mock_redis.lrange.return_value = []
    _fake_aioredis.from_url = MagicMock(return_value=mock_redis)

    # Force reimport to pick up the mock
    sys.modules.pop("astromech.memory.backends.redis_conv", None)
    from astromech.memory.backends.redis_conv import RedisConversationBackend

    backend = RedisConversationBackend("redis://localhost:6379")
    turn = ConversationTurn(role="user", content="hi", timestamp=datetime.now())
    await backend.save_turn("s1", turn)
    mock_redis.rpush.assert_called_once()


@pytest.mark.asyncio
async def test_redis_conv_clear():
    mock_redis = AsyncMock()
    _fake_aioredis.from_url = MagicMock(return_value=mock_redis)

    sys.modules.pop("astromech.memory.backends.redis_conv", None)
    from astromech.memory.backends.redis_conv import RedisConversationBackend

    backend = RedisConversationBackend("redis://localhost:6379")
    await backend.clear("s1")
    mock_redis.delete.assert_called_once_with("conv:s1")


@pytest.mark.asyncio
async def test_redis_conv_get_history():
    now = datetime.now()
    turn_data = json.dumps({
        "role": "user",
        "content": "hello",
        "timestamp": now.isoformat(),
        "metadata": {},
        "token_count": 5,
    })
    mock_redis = AsyncMock()
    mock_redis.lrange.return_value = [turn_data.encode()]
    _fake_aioredis.from_url = MagicMock(return_value=mock_redis)

    sys.modules.pop("astromech.memory.backends.redis_conv", None)
    from astromech.memory.backends.redis_conv import RedisConversationBackend

    backend = RedisConversationBackend("redis://localhost:6379")
    history = await backend.get_history("s1")
    assert len(history) == 1
    assert history[0].content == "hello"
    assert history[0].role == "user"


@pytest.mark.asyncio
async def test_redis_conv_summary():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"summary text"
    _fake_aioredis.from_url = MagicMock(return_value=mock_redis)

    sys.modules.pop("astromech.memory.backends.redis_conv", None)
    from astromech.memory.backends.redis_conv import RedisConversationBackend

    backend = RedisConversationBackend("redis://localhost:6379")
    await backend.save_summary("s1", "summary text")
    mock_redis.set.assert_called_once()

    result = await backend.get_summary("s1")
    assert result == "summary text"


# ===================== SQLite conversation backend tests =====================

@pytest.fixture
def _inject_aiosqlite():
    """Try to use real aiosqlite; skip if not installed."""
    pytest.importorskip("aiosqlite")


@pytest.mark.asyncio
@pytest.mark.usefixtures("_inject_aiosqlite")
async def test_sqlite_conv_save_and_get():
    from astromech.memory.backends.sqlite_conv import SQLiteConversationBackend
    backend = SQLiteConversationBackend(":memory:")
    await backend.initialize()
    turn = ConversationTurn(role="user", content="hello", timestamp=datetime.now(), token_count=5)
    await backend.save_turn("s1", turn)
    history = await backend.get_history("s1")
    assert len(history) == 1
    assert history[0].content == "hello"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_inject_aiosqlite")
async def test_sqlite_conv_clear():
    from astromech.memory.backends.sqlite_conv import SQLiteConversationBackend
    backend = SQLiteConversationBackend(":memory:")
    await backend.initialize()
    turn = ConversationTurn(role="user", content="hi", timestamp=datetime.now())
    await backend.save_turn("s1", turn)
    await backend.clear("s1")
    history = await backend.get_history("s1")
    assert len(history) == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("_inject_aiosqlite")
async def test_sqlite_conv_summary():
    from astromech.memory.backends.sqlite_conv import SQLiteConversationBackend
    backend = SQLiteConversationBackend(":memory:")
    await backend.initialize()
    await backend.save_summary("s1", "this is a summary")
    result = await backend.get_summary("s1")
    assert result == "this is a summary"


# ===================== PostgreSQL conversation backend tests =====================

def _make_pg_mock_pool(mock_conn):
    """Create a mock asyncpg pool where acquire() returns an async context manager."""
    mock_pool = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    mock_pool.acquire.return_value = ctx
    return mock_pool


@pytest.mark.asyncio
async def test_pg_conv_save():
    mock_conn = AsyncMock()
    mock_pool = _make_pg_mock_pool(mock_conn)

    sys.modules.pop("astromech.memory.backends.pg_conv", None)
    from astromech.memory.backends.pg_conv import PGConversationBackend

    backend = PGConversationBackend(pool=mock_pool)
    turn = ConversationTurn(role="user", content="hi", timestamp=datetime.now())
    await backend.save_turn("s1", turn)
    mock_conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_pg_conv_get_history():
    mock_conn = AsyncMock()
    mock_pool = _make_pg_mock_pool(mock_conn)

    now = datetime.now()
    mock_conn.fetch.return_value = [
        {"role": "user", "content": "hello", "metadata": "{}", "token_count": 3, "timestamp": now},
    ]

    sys.modules.pop("astromech.memory.backends.pg_conv", None)
    from astromech.memory.backends.pg_conv import PGConversationBackend

    backend = PGConversationBackend(pool=mock_pool)
    history = await backend.get_history("s1")
    assert len(history) == 1
    assert history[0].content == "hello"


# ===================== FAISS semantic backend tests =====================

@pytest.fixture
def _inject_faiss():
    """Skip if numpy/faiss not installed."""
    pytest.importorskip("numpy")
    pytest.importorskip("faiss")


@pytest.mark.usefixtures("_inject_faiss")
def test_faiss_store_and_search():
    # Re-import to get the real module
    sys.modules.pop("astromech.memory.backends.faiss_sem", None)
    from astromech.memory.backends.faiss_sem import FAISSSemanticBackend
    backend = FAISSSemanticBackend(dimension=4)
    import asyncio

    async def run():
        await backend.store("agent1", "fact 1", [0.1, 0.2, 0.3, 0.4], {"source": "test"})
        await backend.store("agent1", "fact 2", [0.1, 0.2, 0.3, 0.5], {"source": "test"})
        results = await backend.search("agent1", [0.1, 0.2, 0.3, 0.4], top_k=2)
        assert len(results) >= 1
        assert results[0].content == "fact 1"

    asyncio.run(run())


# ===================== Memory strategies tests =====================

def test_sliding_window():
    from astromech.memory.strategies.sliding_window import SlidingWindowStrategy
    turns = [
        ConversationTurn(role="user", content=f"msg{i}", timestamp=datetime.now())
        for i in range(20)
    ]
    strategy = SlidingWindowStrategy()
    result = strategy.apply(turns, max_turns=5)
    assert len(result) == 5
    # Should be the last 5 turns
    assert result[0].content == "msg15"
    assert result[-1].content == "msg19"


def test_sliding_window_under_limit():
    from astromech.memory.strategies.sliding_window import SlidingWindowStrategy
    turns = [
        ConversationTurn(role="user", content=f"msg{i}", timestamp=datetime.now())
        for i in range(3)
    ]
    strategy = SlidingWindowStrategy()
    result = strategy.apply(turns, max_turns=5)
    assert len(result) == 3


def test_token_budget():
    from astromech.memory.strategies.token_budget import TokenBudgetStrategy
    turns = [
        ConversationTurn(role="user", content=f"msg{i}", timestamp=datetime.now(), token_count=100)
        for i in range(10)
    ]
    strategy = TokenBudgetStrategy()
    result = strategy.apply(turns, budget=350)
    assert len(result) <= 4
    # With budget 350 and 100 tokens each, should get exactly 3 turns
    assert len(result) == 3


def test_token_budget_empty():
    from astromech.memory.strategies.token_budget import TokenBudgetStrategy
    strategy = TokenBudgetStrategy()
    result = strategy.apply([], budget=1000)
    assert len(result) == 0


def test_summary_strategy():
    from astromech.memory.strategies.summary import SummaryStrategy
    turns = [
        ConversationTurn(role="user", content=f"msg{i}", timestamp=datetime.now())
        for i in range(10)
    ]

    def mock_summary_fn(older_turns):
        return f"Summary of {len(older_turns)} turns"

    strategy = SummaryStrategy()
    result = strategy.apply(turns, summary_fn=mock_summary_fn, recent_count=3)
    assert result["summary"] == "Summary of 7 turns"
    assert len(result["recent"]) == 3


def test_summary_strategy_short_history():
    from astromech.memory.strategies.summary import SummaryStrategy
    turns = [
        ConversationTurn(role="user", content=f"msg{i}", timestamp=datetime.now())
        for i in range(2)
    ]
    strategy = SummaryStrategy()
    result = strategy.apply(turns, summary_fn=lambda x: "unused", recent_count=5)
    assert result["summary"] is None
    assert len(result["recent"]) == 2
