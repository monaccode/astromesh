import json

import pytest

from astromesh.core import tokens
from astromesh.orchestration.observaciones import DEFAULT_MAX_TOOL_RESULT_TOKENS, presentar


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


def test_default_es_8000():
    assert DEFAULT_MAX_TOOL_RESULT_TOKENS == 8000


def test_string_que_entra_va_tal_cual():
    assert presentar("hola", 100) == ("hola", {"tokens": 1, "truncated": False, "omitted": 0})


def test_dict_se_serializa_como_json_no_repr():
    texto, meta = presentar({"ok": True, "nada": None, "ñ": "año"}, 100)
    assert texto == '{"ok":true,"nada":null,"ñ":"año"}'
    assert meta["truncated"] is False


def test_none_y_vacio():
    assert presentar(None, 100)[0] == "null"
    assert presentar("", 100)[0] == ""


def test_lista_que_no_entra_conserva_el_principio_y_avisa():
    filas = [{"id": i, "nombre": "x" * 36} for i in range(200)]  # ~13 tokens c/u
    texto, meta = presentar(filas, 300)
    datos = json.loads(texto)  # JSON válido
    assert datos[0] == {"id": 0, "nombre": "x" * 36}
    aviso = datos[-1]
    assert set(aviso) == {"_omitidos", "_nota"}
    assert aviso["_omitidos"] == 200 - (len(datos) - 1)
    assert meta == {"tokens": meta["tokens"], "truncated": True, "omitted": aviso["_omitidos"]}
    assert meta["tokens"] > 300
    assert tokens.estimate_tokens(texto) <= 300


def test_dict_con_lista_grande_recorta_esa_lista_y_deja_el_resto():
    obs = {"total": 500, "data": [{"id": i, "v": "y" * 40} for i in range(500)], "ok": True}
    texto, meta = presentar(obs, 400)
    datos = json.loads(texto)
    assert datos["total"] == 500
    assert datos["ok"] is True
    assert datos["data"][-1]["_omitidos"] == meta["omitted"]
    assert meta["omitted"] > 0
    assert tokens.estimate_tokens(texto) <= 400


def test_sub_agente_conserva_answer_y_recorta_data():
    obs = {"answer": "listo", "data": ["z" * 100 for _ in range(300)]}
    texto, _ = presentar(obs, 500)
    datos = json.loads(texto)
    assert datos["answer"] == "listo"
    assert "_omitidos" in datos["data"][-1]


def test_texto_que_no_entra_lleva_marcador():
    texto, meta = presentar("a" * 4000, 100)  # 1000 tokens
    assert texto.endswith("[resultado recortado: 100 de 1000 tokens]")
    assert meta == {"tokens": 1000, "truncated": True, "omitted": 0}


def test_dict_sin_listas_que_no_entra_cae_a_texto():
    texto, meta = presentar({"blob": "b" * 4000}, 100)
    assert "[resultado recortado:" in texto
    assert meta["truncated"] is True
    assert meta["omitted"] == 0


def test_un_elemento_mas_grande_que_el_presupuesto_cae_a_texto():
    texto, _meta = presentar([{"blob": "c" * 4000}], 100)
    assert "[resultado recortado:" in texto
    assert texto.startswith('[{"blob":"ccc')


def test_presupuesto_minimo_no_explota():
    texto, meta = presentar("d" * 400, 1)
    assert "[resultado recortado:" in texto
    assert meta["truncated"] is True


def test_no_serializable_usa_default_str():
    class Raro:
        def __str__(self):
            return "raro"

    assert presentar({"x": Raro()}, 100)[0] == '{"x":"raro"}'
