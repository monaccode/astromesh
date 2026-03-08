from typing import Any, Callable

from astromesh.core.memory import ConversationTurn


class SummaryStrategy:
    def apply(
        self,
        history: list[ConversationTurn],
        summary_fn: Callable[[list[ConversationTurn]], str],
        recent_count: int = 5,
    ) -> dict[str, Any]:
        if len(history) <= recent_count:
            return {
                "summary": None,
                "recent": list(history),
            }
        older = history[:-recent_count]
        recent = history[-recent_count:]
        summary = summary_fn(older)
        return {
            "summary": summary,
            "recent": list(recent),
        }
