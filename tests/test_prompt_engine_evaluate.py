"""`PromptEngine.evaluate`: el `when` de `spec.prefetch` es una EXPRESIÓN, no un
string renderizado. `{{ rows }}` de una lista vacía renderiza "[]", que no es
vacío: evaluado como string, una búsqueda correría sin la persona."""

from astromesh.core.prompt_engine import PromptEngine


def test_una_lista_vacia_es_falsa_aunque_renderizada_no_sea_vacia():
    pe = PromptEngine()
    assert pe.render("{{ x }}", {"x": []}) == "[]"
    assert not pe.evaluate("x", {"x": []})


def test_una_variable_indefinida_da_none():
    assert PromptEngine().evaluate("sender_phone", {}) is None


def test_el_and_corta_antes_de_leer_un_atributo_de_algo_indefinido():
    pe = PromptEngine()
    expr = "prefetch.persona and prefetch.persona.success and prefetch.persona.data.rows"
    assert pe.evaluate(expr, {"prefetch": {}}) is None
    persona = {"persona": {"success": True, "data": {"rows": [1]}}}
    assert pe.evaluate(expr, {"prefetch": persona}) == [1]
