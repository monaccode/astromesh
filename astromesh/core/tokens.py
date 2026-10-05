"""Conteo de tokens y ventana de contexto, sin dependencias nuevas.

litellm es un extra opcional: se importa perezoso y cualquier falla cae al
estimador `len/4`. `astromesh/api/main.py` tiene que seguir importando sin
extras o la imagen de astromesh-os no bootea.
"""

import logging
import math

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_WINDOW = 32_000


def _litellm():
    try:
        import litellm
    except ImportError:
        return None
    return litellm


def estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    lib = _litellm()
    if lib is not None:
        try:
            return int(lib.token_counter(text=text))
        except Exception:
            logger.debug("litellm.token_counter falló; uso len/4", exc_info=True)
    return math.ceil(len(text) / 4)


def _candidate_window(block: dict) -> tuple[int, str] | None:
    if block.get("context_window"):
        return int(block["context_window"]), "yaml"
    if (block.get("source") or block.get("provider")) == "ollama":
        num_ctx = (block.get("parameters") or {}).get("num_ctx")
        if num_ctx:
            return int(num_ctx), "ollama.num_ctx"
    lib = _litellm()
    if lib is not None and block.get("model"):
        try:
            n = lib.get_model_info(block["model"]).get("max_input_tokens")
            if n:
                return int(n), "litellm"
        except Exception:
            logger.debug("litellm no conoce %r", block.get("model"), exc_info=True)
    return None


def resolve_context_window(candidates: list[dict]) -> tuple[int, str]:
    """La ventana MÍNIMA entre candidatos: un fallback chico no debe desbordar."""
    found = [w for w in map(_candidate_window, candidates) if w]
    if not found:
        return DEFAULT_CONTEXT_WINDOW, "default"
    return min(found)
