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


def _recortar_lista(lista: list, armar, max_tokens: int):
    """El prefijo más largo de `lista` tal que `armar(prefijo + [aviso])` entra.

    `armar` envuelve la lista recortada en el objeto completo (la lista sola, o
    el dict con esa clave reemplazada). Devuelve (texto, omitidos) o None si ni
    un elemento entra.
    """
    lo, hi, mejor = 1, len(lista) - 1, None
    while lo <= hi:
        k = (lo + hi) // 2
        texto = _serializar(armar([*lista[:k], _aviso(len(lista) - k)]))
        if estimate_tokens(texto) <= max_tokens:
            mejor, lo = (texto, len(lista) - k), k + 1
        else:
            hi = k - 1
    return mejor


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
            listas = [
                (estimate_tokens(_serializar(v)), k)
                for k, v in observacion.items()
                if isinstance(v, list) and len(v) > 1
            ]
            if listas:
                _, clave = max(listas)
                r = _recortar_lista(
                    observacion[clave],
                    lambda xs: {**observacion, clave: xs},
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
