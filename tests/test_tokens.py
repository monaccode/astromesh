import types

import pytest

from astromesh.core import tokens
from astromesh.core.tokens import DEFAULT_CONTEXT_WINDOW, estimate_tokens, resolve_context_window


@pytest.fixture
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


def _fake_litellm(max_input=None, count=None, falla=False):
    def get_model_info(model):
        if falla or max_input is None:
            raise Exception("modelo desconocido")
        return {"max_input_tokens": max_input}

    def token_counter(model="", text=""):
        if falla:
            raise Exception("tokenizer roto")
        return count

    return types.SimpleNamespace(get_model_info=get_model_info, token_counter=token_counter)


def test_estimate_sin_litellm_es_len_sobre_4(sin_litellm):
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


def test_estimate_usa_litellm_si_esta(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: _fake_litellm(count=7))
    assert estimate_tokens("hola mundo") == 7


def test_estimate_cae_a_len_si_litellm_falla(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: _fake_litellm(falla=True))
    assert estimate_tokens("abcdefgh") == 2


def test_ventana_yaml_gana(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: _fake_litellm(max_input=128_000))
    cand = {
        "provider": "ollama",
        "model": "x",
        "context_window": 8000,
        "parameters": {"num_ctx": 4096},
    }
    assert resolve_context_window([cand]) == (8000, "yaml")


def test_ventana_num_ctx_de_ollama(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: _fake_litellm(max_input=128_000))
    cand = {"source": "ollama", "model": "x", "parameters": {"num_ctx": 4096}}
    assert resolve_context_window([cand]) == (4096, "ollama.num_ctx")


def test_ventana_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: _fake_litellm(max_input=128_000))
    assert resolve_context_window([{"provider": "openai", "model": "gpt-4o"}]) == (
        128_000,
        "litellm",
    )


def test_ventana_default(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: _fake_litellm(falla=True))
    assert resolve_context_window([{"provider": "openai", "model": "raro"}]) == (
        DEFAULT_CONTEXT_WINDOW,
        "default",
    )
    assert resolve_context_window([]) == (DEFAULT_CONTEXT_WINDOW, "default")


def test_ventana_es_la_minima_entre_candidatos(sin_litellm):
    cands = [
        {"provider": "openai", "model": "a", "context_window": 200_000},
        {"provider": "ollama", "model": "b", "parameters": {"num_ctx": 32_768}},
    ]
    assert resolve_context_window(cands) == (32_768, "ollama.num_ctx")
