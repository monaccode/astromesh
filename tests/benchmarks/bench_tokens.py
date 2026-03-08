"""Benchmarks for token budget strategy."""
import os
from datetime import datetime, timezone

import pytest
from astromesh.core.memory import ConversationTurn


def make_history(n_turns):
    now = datetime.now(timezone.utc)
    return [
        ConversationTurn(
            role="user", content=f"Message number {i} with some content here",
            timestamp=now, token_count=10
        )
        for i in range(n_turns)
    ]


@pytest.mark.benchmark
class TestTokenBudgetBenchmark:
    @pytest.fixture(params=[10, 100, 1000], ids=["10-turns", "100-turns", "1000-turns"])
    def history(self, request):
        return make_history(request.param)

    def test_native(self, benchmark, history):
        os.environ.pop("ASTROMESH_FORCE_PYTHON", None)
        from astromesh.memory.strategies.token_budget import TokenBudgetStrategy
        strategy = TokenBudgetStrategy()
        benchmark(strategy.apply, history, 500)

    def test_python(self, benchmark, history):
        os.environ["ASTROMESH_FORCE_PYTHON"] = "1"
        from astromesh.memory.strategies.token_budget import TokenBudgetStrategy
        strategy = TokenBudgetStrategy()
        benchmark(strategy.apply, history, 500)
