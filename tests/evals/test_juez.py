"""El juez: veredicto, respuestas inválidas y tokens aparte."""

from astromesh.evals.juez import juzgar
from astromesh.providers.base import CompletionResponse


class _Juez:
    def __init__(self, contenido=None, levanta=False):
        self.contenido, self.levanta, self.mensajes = contenido, levanta, None

    async def complete(self, messages, **kw):
        self.mensajes = messages
        if self.levanta:
            raise RuntimeError("caído")
        return CompletionResponse(
            content=self.contenido,
            model="j",
            provider="p",
            usage={"input_tokens": 30, "output_tokens": 5},
            latency_ms=1.0,
            cost=0.0,
        )


async def test_veredicto_valido_y_prompt_con_rubrica():
    j = _Juez('{"score": 0.8, "reason": "bien"}')
    v = await juzgar(j, "dice la cantidad", ["¿stock?"], "hay 12")
    assert (v.score, v.reason, v.tokens, v.error) == (0.8, "bien", 35, None)
    texto = j.mensajes[-1]["content"]
    assert "dice la cantidad" in texto
    assert "¿stock?" in texto
    assert "hay 12" in texto


async def test_acepta_json_en_fence():
    v = await juzgar(_Juez('```json\n{"score": 1, "reason": "ok"}\n```'), "r", ["q"], "a")
    assert v.score == 1.0
    assert v.error is None


async def test_no_json_es_error():
    v = await juzgar(_Juez("me parece bien"), "r", ["q"], "a")
    assert v.score is None
    assert v.error


async def test_score_fuera_de_rango_es_error():
    v = await juzgar(_Juez('{"score": 7, "reason": "x"}'), "r", ["q"], "a")
    assert v.score is None
    assert v.error


async def test_provider_que_levanta_es_error():
    v = await juzgar(_Juez(levanta=True), "r", ["q"], "a")
    assert v.score is None
    assert "caído" in v.error
    assert v.tokens == 0
