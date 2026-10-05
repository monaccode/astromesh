from datetime import UTC, datetime

import pytest

from astromesh.core import tokens
from astromesh.core.memory import ConversationBackend, ConversationTurn, MemoryManager


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


def _t(role, content, n=0):
    return ConversationTurn(role=role, content=content, timestamp=datetime.now(UTC), token_count=n)


class Fake(ConversationBackend):
    def __init__(self, turns=None, summary=None):
        self.turns = list(turns or [])
        self.summary = summary
        self.saved_summary = None

    async def save_turn(self, session_id, turn):
        self.turns.append(turn)

    async def get_history(self, session_id, limit=50):
        return list(self.turns[-limit:])

    async def clear(self, session_id):
        self.turns = []

    async def get_summary(self, session_id):
        return self.summary

    async def save_summary(self, session_id, summary):
        self.saved_summary = summary


async def test_persist_carga_token_count():
    backend = Fake()
    mgr = MemoryManager("a", {"conversational": {}}, conversation=backend)
    await mgr.persist_turn("s", _t("user", "x" * 40))
    await mgr.persist_turn("s", _t("assistant", "y" * 80))
    assert [t.token_count for t in backend.turns] == [10, 20]


async def test_build_context_estima_filas_viejas_con_cero():
    backend = Fake([_t("user", "x" * 40, n=0)])
    mgr = MemoryManager("a", {"conversational": {}}, conversation=backend)
    ctx = await mgr.build_context("s", "q")
    assert ctx["conversation"][0].token_count == 10


async def test_token_budget_recorta_y_se_queda_con_lo_ultimo():
    turns = [_t("user" if i % 2 == 0 else "assistant", f"{i:02d}" + "x" * 398) for i in range(40)]
    mgr = MemoryManager(
        "a", {"conversational": {"strategy": "token_budget"}}, conversation=Fake(turns)
    )
    ctx = await mgr.build_context("s", "q")
    stats = mgr.fit_history(ctx, 1000)  # 100 tokens por turno → entran 10
    assert stats["turns_kept"] == 10
    assert stats["turns_dropped"] == 30
    assert ctx["conversation"][-1] is turns[-1]


async def test_build_context_sin_presupuesto_no_recorta():
    turns = [_t("user", "x" * 400) for _ in range(30)]
    mgr = MemoryManager(
        "a", {"conversational": {"strategy": "token_budget"}}, conversation=Fake(turns)
    )
    ctx = await mgr.build_context("s", "q")
    assert len(ctx["conversation"]) == 30


async def test_summary_carga_el_resumen_y_lo_cuenta():
    turns = [_t("user", "x" * 400) for _ in range(5)]
    mgr = MemoryManager(
        "a",
        {"conversational": {"strategy": "summary"}},
        conversation=Fake(turns, summary="z" * 400),
    )
    ctx = await mgr.build_context("s", "q")
    stats = mgr.fit_history(ctx, 300)  # 100 del resumen + 2 turnos de 100
    assert ctx["conversation_summary"] == "z" * 400
    assert stats["summary_used"] is True
    assert stats["turns_kept"] == 2


async def test_resumen_que_no_entra_se_descarta_sin_lanzar():
    mgr = MemoryManager(
        "a",
        {"conversational": {"strategy": "summary"}},
        conversation=Fake([_t("user", "x" * 40)], summary="z" * 4000),
    )
    ctx = await mgr.build_context("s", "q")
    stats = mgr.fit_history(ctx, 50)
    assert ctx["conversation_summary"] is None
    assert stats["summary_used"] is False
    assert stats["turns_kept"] == 1


async def test_presupuesto_cero_deja_historial_vacio():
    mgr = MemoryManager("a", {"conversational": {}}, conversation=Fake([_t("user", "hola")]))
    ctx = await mgr.build_context("s", "q")
    assert mgr.fit_history(ctx, 0)["turns_kept"] == 0
    assert ctx["conversation"] == []


async def test_falla_del_resumen_no_rompe_persist():
    async def explota(turns):
        raise RuntimeError("rol caído")

    backend = Fake([_t("user", "x") for _ in range(30)])
    mgr = MemoryManager(
        "a", {"conversational": {"max_turns": 20}}, conversation=backend, summarize_fn=explota
    )
    await mgr.persist_turn("s", _t("user", "y"))  # no lanza
    assert backend.saved_summary is None
