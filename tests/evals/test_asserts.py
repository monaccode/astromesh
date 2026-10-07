"""Cada assert pasa y falla."""

import pytest

from astromesh.evals.asserts import chequear


@pytest.mark.parametrize(
    ("asercion", "respuesta", "tools", "pasa"),
    [
        ({"contains": "DOCE"}, "hay doce unidades", [], True),
        ({"contains": "trece"}, "hay doce unidades", [], False),
        ({"not_contains": "no sé"}, "hay 12", [], True),
        ({"not_contains": "NO SÉ"}, "no sé", [], False),
        ({"regex": r"\b12\b"}, "hay 12", [], True),
        ({"regex": "Hay"}, "hay 12", [], False),
        ({"regex": "(?i)HAY"}, "hay 12", [], True),
        ({"equals": "ok"}, "  ok\n", [], True),
        ({"equals": "ok"}, "ok.", [], False),
        ({"tool_called": "stock"}, "", ["precio", "stock"], True),
        ({"tool_called": "stock"}, "", ["precio"], False),
        ({"tool_not_called": "borrar"}, "", ["stock"], True),
        ({"tool_not_called": "borrar"}, "", ["borrar"], False),
    ],
)
def test_chequear(asercion, respuesta, tools, pasa):
    motivo = chequear(asercion, respuesta, tools)
    assert (motivo is None) is pasa
    if not pasa:
        assert isinstance(motivo, str)
        assert motivo
