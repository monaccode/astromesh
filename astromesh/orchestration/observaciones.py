"""Cómo entra el resultado de una tool al mensaje del modelo.

Un resultado sin tope se paga entero la primera vez y ocupa ventana; el
reenvío en las vueltas siguientes lo sirve el caché de prefijo, así que el
tope va en el momento en que la observación ENTRA, nunca reescribiendo las
anteriores (rompería el prefijo). Glyph no pasa por acá: sus programas usan
los resultados como datos, y recortarlos cambiaría lo que calculan.
"""

import json
import logging
import math

from astromesh.core.tokens import estimate_tokens

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOOL_RESULT_TOKENS = 8000


def _serializar(obs) -> str:
    if isinstance(obs, str):
        return obs
    return json.dumps(obs, ensure_ascii=False, separators=(",", ":"), default=str)


def _aviso(n: int) -> dict:
    return {
        "_omitidos": n,
        "_nota": f"resultado recortado: hay {n} elementos más; pedí un filtro más específico",
    }


def _barato(texto: str) -> int:
    return math.ceil(len(texto) / 4)


def _recortar_lista(lista: list, armar, max_tokens: int):
    """El prefijo más largo de `lista` tal que `armar(prefijo + [aviso])` entra.

    `armar` envuelve la lista recortada en el objeto completo (la lista sola, o
    el dict con esa clave reemplazada). Devuelve (texto, omitidos) o None si ni
    un elemento entra.

    La búsqueda sondea con `len/4` (el tokenizer real cuesta por sondeo) y sólo
    el candidato elegido se verifica con `estimate_tokens`; si no entra, k baja
    en proporción al exceso hasta que entre.
    """

    def texto_de(k):
        return _serializar(armar([*lista[:k], _aviso(len(lista) - k)]))

    lo, hi, k = 1, len(lista) - 1, 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if _barato(texto_de(mid)) <= max_tokens:
            k, lo = mid, mid + 1
        else:
            hi = mid - 1
    k = k or 1
    while k >= 1:  # k baja estricto en cada vuelta: termina
        texto = texto_de(k)
        reales = estimate_tokens(texto)
        if reales <= max_tokens:
            return texto, len(lista) - k
        k = min(k - 1, k * max_tokens // reales)
    return None


def _listas(obj, camino=()):
    """(tamaño, camino) de cada lista con más de un elemento, bajando sólo por dicts."""
    for clave, v in obj.items():
        if isinstance(v, list) and len(v) > 1:
            yield len(_serializar(v)), (*camino, clave)
        elif isinstance(v, dict):
            yield from _listas(v, (*camino, clave))


def _reemplazar(obj: dict, camino: tuple, xs: list) -> dict:
    clave, *resto = camino
    return {**obj, clave: _reemplazar(obj[clave], resto, xs) if resto else xs}


def _recorte_de_texto(texto: str, total: int, max_tokens: int) -> str:
    marcador = f"\n[resultado recortado: {max_tokens} de {total} tokens]"
    # ponytail: corte por caracteres con la proporción de tokens; el marcador
    # puede pasar el tope por unos pocos tokens.
    largo = max(0, math.floor(len(texto) * max_tokens / max(total, 1)) - len(marcador))
    return texto[:largo] + marcador


def presentar(observacion, max_tokens: int) -> tuple[str, dict]:
    try:
        texto = _serializar(observacion)
        total = estimate_tokens(texto)
        if total <= max_tokens:
            return texto, {"tokens": total, "truncated": False, "omitted": 0}
        if isinstance(observacion, list) and len(observacion) > 1:
            r = _recortar_lista(observacion, lambda xs: xs, max_tokens)
            if r:
                return r[0], {"tokens": total, "truncated": True, "omitted": r[1]}
        if isinstance(observacion, dict):
            listas = list(_listas(observacion))
            if listas:
                _, camino = max(listas, key=lambda t: t[0])
                lista = observacion
                for clave in camino:
                    lista = lista[clave]
                r = _recortar_lista(
                    lista,
                    lambda xs: _reemplazar(observacion, camino, xs),
                    max_tokens,
                )
                if r:
                    return r[0], {"tokens": total, "truncated": True, "omitted": r[1]}
        return _recorte_de_texto(texto, total, max_tokens), {
            "tokens": total,
            "truncated": True,
            "omitted": 0,
        }
    except Exception:
        logger.debug("presentar falló; recorte de texto plano", exc_info=True)
        crudo = str(observacion)
        total = estimate_tokens(crudo)
        if total <= max_tokens:
            return crudo, {"tokens": total, "truncated": False, "omitted": 0}
        return _recorte_de_texto(crudo, total, max_tokens), {
            "tokens": total,
            "truncated": True,
            "omitted": 0,
        }
