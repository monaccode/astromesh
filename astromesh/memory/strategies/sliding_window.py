from astromesh.core.memory import ConversationTurn


class SlidingWindowStrategy:
    def apply(self, history: list[ConversationTurn], max_turns: int = 20) -> list[ConversationTurn]:
        if len(history) <= max_turns:
            return list(history)
        return list(history[-max_turns:])
