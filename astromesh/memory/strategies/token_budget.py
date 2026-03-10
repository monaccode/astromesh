import os

from astromesh.core.memory import ConversationTurn

try:
    from astromesh._native import RustTokenBudget

    _HAS_NATIVE = True
except ImportError:
    _HAS_NATIVE = False


class TokenBudgetStrategy:
    def apply(self, history: list[ConversationTurn], budget: int = 4096) -> list[ConversationTurn]:
        if _HAS_NATIVE and history and not os.environ.get("ASTROMESH_FORCE_PYTHON"):
            contents = [t.content for t in history]
            counts = [t.token_count for t in history]
            indices = RustTokenBudget.apply(contents, counts, budget)
            return [history[i] for i in indices]

        selected: list[ConversationTurn] = []
        used = 0
        for turn in reversed(history):
            cost = turn.token_count if turn.token_count > 0 else len(turn.content.split())
            if used + cost > budget:
                break
            selected.insert(0, turn)
            used += cost
        return selected
