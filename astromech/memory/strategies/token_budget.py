from astromech.core.memory import ConversationTurn


class TokenBudgetStrategy:
    def apply(self, history: list[ConversationTurn], budget: int = 4096) -> list[ConversationTurn]:
        selected: list[ConversationTurn] = []
        used = 0
        for turn in reversed(history):
            cost = turn.token_count if turn.token_count > 0 else len(turn.content.split())
            if used + cost > budget:
                break
            selected.insert(0, turn)
            used += cost
        return selected
