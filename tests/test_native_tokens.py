"""Tests for native token budget strategy."""
from datetime import datetime, timezone

from astromesh.core.memory import ConversationTurn


class TestTokenBudget:
    def _make_turns(self, contents, token_counts=None):
        turns = []
        for i, content in enumerate(contents):
            tc = token_counts[i] if token_counts else 0
            turns.append(ConversationTurn(
                role="user", content=content,
                timestamp=datetime.now(timezone.utc), token_count=tc
            ))
        return turns

    def test_empty_history(self, use_native):
        from astromesh.memory.strategies.token_budget import TokenBudgetStrategy
        strategy = TokenBudgetStrategy()
        assert strategy.apply([], budget=100) == []

    def test_all_fit(self, use_native):
        from astromesh.memory.strategies.token_budget import TokenBudgetStrategy
        strategy = TokenBudgetStrategy()
        turns = self._make_turns(["hello", "world"], [5, 5])
        result = strategy.apply(turns, budget=100)
        assert len(result) == 2

    def test_budget_exceeded(self, use_native):
        from astromesh.memory.strategies.token_budget import TokenBudgetStrategy
        strategy = TokenBudgetStrategy()
        turns = self._make_turns(["a" * 100, "b" * 100, "c" * 100], [50, 50, 50])
        result = strategy.apply(turns, budget=80)
        # Only last turn fits
        assert len(result) == 1
        assert result[0].content == "c" * 100

    def test_fallback_word_count(self, use_native):
        from astromesh.memory.strategies.token_budget import TokenBudgetStrategy
        strategy = TokenBudgetStrategy()
        turns = self._make_turns(["one two three", "four five"], [0, 0])
        result = strategy.apply(turns, budget=10)
        assert len(result) == 2
