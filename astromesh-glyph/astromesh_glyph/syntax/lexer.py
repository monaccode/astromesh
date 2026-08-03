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


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    indents = [0]
    lines = source.splitlines()

    for lineno, raw in enumerate(lines, start=1):
        stripped = raw.lstrip(" ")
        indent = len(raw) - len(stripped)

        if "\t" in raw[:indent] or stripped.startswith("\t"):
            raise GlyphSyntaxError("tabulador en la indentación: usá espacios", lineno, 1)
        if not stripped or stripped.startswith("#"):
            continue

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

        tokens.extend(_tokenize_line(stripped, lineno, indent))
        tokens.append(Token(TokenType.NEWLINE, "\n", lineno, len(raw) + 1))

    while len(indents) > 1:
        indents.pop()
        tokens.append(Token(TokenType.DEDENT, "", len(lines) + 1, 1))
    tokens.append(Token(TokenType.EOF, "", len(lines) + 1, 1))
    return tokens


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

        if ch.isdigit():
            j = i
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
