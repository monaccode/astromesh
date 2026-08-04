"""Tokenizador de Glyph.

Bloques por indentación, como Python: sólo espacios, y la profundidad tiene que
coincidir exactamente con un nivel abierto. Un tabulador es un error duro — la
alternativa (tratarlo como N espacios) hace que dos programas visualmente
idénticos parseen distinto, y el modelo no tiene forma de ver la diferencia.
"""

from __future__ import annotations

from astromesh_glyph.errors import GlyphSyntaxError
from astromesh_glyph.syntax.tokens import Token, TokenType

_TWO_CHAR_OPS = frozenset({"==", "!=", ">=", "<="})
_ONE_CHAR_OPS = frozenset({"=", ">", "<", "|", "(", ")", "{", "}", "[", "]", ",", ":", "."})
_OPENERS = {"(": ")", "{": "}", "[": "]"}
_CLOSERS = {v: k for k, v in _OPENERS.items()}


def tokenize(source: str) -> list[Token]:
    """Tokeniza un programa Glyph.

    Dentro de corchetes abiertos hay **continuación implícita**, igual que en
    Python: no se emite NEWLINE ni se mira la indentación hasta que cierran. Sin
    esto el modelo no puede escribir un dict o una llamada en varias líneas, que
    es lo primero que hace — y era el motivo del fallo de la primera corrida del
    benchmark contra kimi-k2.5.
    """
    tokens: list[Token] = []
    indents = [0]
    open_stack: list[Token] = []
    lines = source.splitlines()

    for lineno, raw in enumerate(lines, start=1):
        stripped = raw.lstrip(" ")
        indent = len(raw) - len(stripped)
        continuing = bool(open_stack)

        if not continuing and ("\t" in raw[:indent] or stripped.startswith("\t")):
            raise GlyphSyntaxError("tabulador en la indentación: usá espacios", lineno, 1)
        if not stripped or stripped.startswith("#"):
            continue

        if not continuing:
            if indent > indents[-1]:
                indents.append(indent)
                tokens.append(Token(TokenType.INDENT, "", lineno, indent + 1))
            while indent < indents[-1]:
                indents.pop()
                tokens.append(Token(TokenType.DEDENT, "", lineno, indent + 1))
            if indent != indents[-1]:
                raise GlyphSyntaxError(
                    "indentación que no coincide con ningún bloque abierto", lineno, indent + 1
                )

        line_tokens = _tokenize_line(stripped, lineno, indent)
        _track_brackets(line_tokens, open_stack)
        tokens.extend(line_tokens)
        if not open_stack:
            tokens.append(Token(TokenType.NEWLINE, "\n", lineno, len(raw) + 1))

    if open_stack:
        unclosed = open_stack[-1]
        raise GlyphSyntaxError(f"`{unclosed.value}` sin cerrar", unclosed.line, unclosed.column)

    while len(indents) > 1:
        indents.pop()
        tokens.append(Token(TokenType.DEDENT, "", len(lines) + 1, 1))
    tokens.append(Token(TokenType.EOF, "", len(lines) + 1, 1))
    return tokens


def _track_brackets(line_tokens: list[Token], open_stack: list[Token]) -> None:
    """Actualiza la pila de corchetes abiertos, verificando que emparejen."""
    for tok in line_tokens:
        if tok.type is not TokenType.OP:
            continue
        if tok.value in _OPENERS:
            open_stack.append(tok)
        elif tok.value in _CLOSERS:
            if not open_stack:
                raise GlyphSyntaxError(f"`{tok.value}` sin abrir", tok.line, tok.column)
            expected = _OPENERS[open_stack[-1].value]
            if tok.value != expected:
                raise GlyphSyntaxError(
                    f"se esperaba `{expected}` y se encontró `{tok.value}`", tok.line, tok.column
                )
            open_stack.pop()


def _tokenize_line(text: str, lineno: int, offset: int) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    while i < len(text):
        ch = text[i]
        col = offset + i + 1

        if ch == " ":
            i += 1
            continue
        if ch == "#":
            break

        if ch in {'"', "'"}:
            end = text.find(ch, i + 1)
            if end == -1:
                raise GlyphSyntaxError("string sin cerrar", lineno, col)
            tokens.append(Token(TokenType.STRING, text[i + 1 : end], lineno, col))
            i = end + 1
            continue

        # El `-` sólo puede iniciar un número negativo: Glyph no tiene aritmética,
        # así que no hay resta con la que confundirlo.
        if ch.isdigit() or (ch == "-" and i + 1 < len(text) and text[i + 1].isdigit()):
            j = i + 1 if ch == "-" else i
            while j < len(text) and (text[j].isdigit() or text[j] == "."):
                j += 1
            tokens.append(Token(TokenType.NUMBER, text[i:j], lineno, col))
            i = j
            continue

        if ch.isalpha() or ch == "_":
            j = i
            while j < len(text) and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tokens.append(Token(TokenType.NAME, text[i:j], lineno, col))
            i = j
            continue

        if text[i : i + 2] in _TWO_CHAR_OPS:
            tokens.append(Token(TokenType.OP, text[i : i + 2], lineno, col))
            i += 2
            continue

        if ch in _ONE_CHAR_OPS:
            tokens.append(Token(TokenType.OP, ch, lineno, col))
            i += 1
            continue

        raise GlyphSyntaxError(f"carácter inesperado {ch!r}", lineno, col)

    return tokens
