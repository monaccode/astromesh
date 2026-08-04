"""Descenso recursivo sobre los tokens de Glyph.

Precedencia, de menor a mayor: `or` < `and` < comparación < `|` < primaria.
El pipe liga más fuerte que las comparaciones a propósito: `a | top(3) == b` no
es una expresión que alguien quiera escribir, mientras que `where(x == 1)` sí, y
ahí el argumento se parsea como expresión completa desde cero.
"""

from __future__ import annotations

from astromesh_glyph.errors import GlyphSyntaxError
from astromesh_glyph.syntax import nodes as n
from astromesh_glyph.syntax.lexer import tokenize
from astromesh_glyph.syntax.tokens import Token, TokenType

_COMPARISONS = frozenset({"==", "!=", ">", "<", ">=", "<="})

# `None`/`True`/`False` son alias de Python. No son sintaxis de Glyph, pero el
# modelo los escribe porque escribe Python, y castigarlo con un round-trip de
# reparación cobra caro un error puramente cosmético.
_CONSTANTS = {
    "true": True,
    "false": False,
    "null": None,
    "True": True,
    "False": False,
    "None": None,
}
_KEYWORDS = frozenset({"if", "else", "return", "and", "or", *_CONSTANTS})


def parse(source: str) -> n.Program:
    return _Parser(tokenize(source)).parse_program()


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    # ---- utilidades ----------------------------------------------------------

    @property
    def _current(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _check(self, type_: TokenType, value: str | None = None) -> bool:
        tok = self._current
        return tok.type is type_ and (value is None or tok.value == value)

    def _accept(self, type_: TokenType, value: str | None = None) -> Token | None:
        if self._check(type_, value):
            return self._advance()
        return None

    def _expect(self, type_: TokenType, value: str | None = None) -> Token:
        tok = self._accept(type_, value)
        if tok is None:
            expected = f"`{value}`" if value else type_.value
            raise GlyphSyntaxError(
                f"se esperaba {expected} y se encontró {self._current.value!r}",
                self._current.line,
                self._current.column,
            )
        return tok

    def _skip_newlines(self) -> None:
        while self._accept(TokenType.NEWLINE):
            pass

    # ---- sentencias ----------------------------------------------------------

    def parse_program(self) -> n.Program:
        body = self._parse_block_body(TokenType.EOF)
        return n.Program(line=1, body=body)

    def _parse_block_body(self, terminator: TokenType) -> list[n.Node]:
        body: list[n.Node] = []
        self._skip_newlines()
        while not self._check(terminator):
            body.append(self._parse_statement())
            self._skip_newlines()
        return body

    def _parse_indented_block(self) -> list[n.Node]:
        self._expect(TokenType.NEWLINE)
        self._expect(TokenType.INDENT)
        body = self._parse_block_body(TokenType.DEDENT)
        self._expect(TokenType.DEDENT)
        return body

    def _parse_statement(self) -> n.Node:
        tok = self._current
        if tok.type is TokenType.NAME and tok.value == "if":
            return self._parse_if()
        if tok.type is TokenType.NAME and tok.value == "return":
            self._advance()
            if self._check(TokenType.NEWLINE):
                return n.Return(line=tok.line, value=None)
            return n.Return(line=tok.line, value=self._parse_expression())

        # Asignación: NAME `=` expr. Se distingue de una llamada suelta mirando
        # un token adelante, porque `x = f()` y `f()` empiezan igual.
        if (
            tok.type is TokenType.NAME
            and tok.value not in _KEYWORDS
            and self._tokens[self._pos + 1].type is TokenType.OP
            and self._tokens[self._pos + 1].value == "="
        ):
            self._advance()
            self._advance()
            return n.Assign(line=tok.line, target=tok.value, value=self._parse_expression())

        return n.ExprStmt(line=tok.line, value=self._parse_expression())

    def _parse_if(self) -> n.If:
        tok = self._expect(TokenType.NAME, "if")
        test = self._parse_expression()
        self._expect(TokenType.OP, ":")
        body = self._parse_indented_block()

        orelse: list[n.Node] = []
        self._skip_newlines()
        if self._check(TokenType.NAME, "else"):
            self._advance()
            self._expect(TokenType.OP, ":")
            orelse = self._parse_indented_block()
        return n.If(line=tok.line, test=test, body=body, orelse=orelse)

    # ---- expresiones ---------------------------------------------------------

    def _parse_expression(self) -> n.Node:
        return self._parse_or()

    def _parse_or(self) -> n.Node:
        left = self._parse_and()
        while self._check(TokenType.NAME, "or"):
            tok = self._advance()
            left = n.BinOp(line=tok.line, op="or", left=left, right=self._parse_and())
        return left

    def _parse_and(self) -> n.Node:
        left = self._parse_comparison()
        while self._check(TokenType.NAME, "and"):
            tok = self._advance()
            left = n.BinOp(line=tok.line, op="and", left=left, right=self._parse_comparison())
        return left

    def _parse_comparison(self) -> n.Node:
        left = self._parse_pipe()
        if self._current.type is TokenType.OP and self._current.value in _COMPARISONS:
            tok = self._advance()
            return n.BinOp(line=tok.line, op=tok.value, left=left, right=self._parse_pipe())
        return left

    def _parse_pipe(self) -> n.Node:
        left = self._parse_primary()
        stages: list[n.Call] = []
        while self._check(TokenType.OP, "|"):
            self._advance()
            stage = self._parse_primary()
            if not isinstance(stage, n.Call):
                raise GlyphSyntaxError(
                    "después de `|` se espera una etapa como where(...) o top(...)",
                    self._current.line,
                    self._current.column,
                )
            stages.append(stage)
        if not stages:
            return left
        return n.Pipe(line=left.line, left=left, stages=stages)

    def _parse_primary(self) -> n.Node:
        tok = self._current

        if tok.type is TokenType.NUMBER:
            self._advance()
            value = float(tok.value) if "." in tok.value else int(tok.value)
            return n.Literal(line=tok.line, value=value)

        if tok.type is TokenType.STRING:
            self._advance()
            return n.Literal(line=tok.line, value=tok.value)

        if tok.type is TokenType.OP and tok.value == "{":
            return self._parse_dict()

        if tok.type is TokenType.OP and tok.value == "[":
            return self._parse_list()

        if tok.type is TokenType.OP and tok.value == "(":
            self._advance()
            inner = self._parse_expression()
            self._expect(TokenType.OP, ")")
            return inner

        if tok.type is TokenType.NAME:
            if tok.value in _CONSTANTS:
                self._advance()
                return n.Literal(line=tok.line, value=_CONSTANTS[tok.value])
            return self._parse_name_chain()

        raise GlyphSyntaxError(f"expresión inesperada: {tok.value!r}", tok.line, tok.column)

    def _parse_name_chain(self) -> n.Node:
        """Resuelve `a`, `a.b`, `a(...)` y `a.b(...)`.

        Un nombre punteado seguido de `(` es una capacidad con nombre compuesto
        (`agent.email_composer`); sin `(` es acceso a atributo sobre un valor.
        """
        first = self._expect(TokenType.NAME)
        parts = [first.value]
        while self._check(TokenType.OP, "."):
            self._advance()
            parts.append(self._expect(TokenType.NAME).value)

        if self._check(TokenType.OP, "("):
            return self._parse_call(".".join(parts), first.line)

        node: n.Node = n.Name(line=first.line, id=parts[0])
        for attr in parts[1:]:
            node = n.Attribute(line=first.line, value=node, attr=attr)
        return node

    def _parse_call(self, func: str, line: int) -> n.Call:
        self._expect(TokenType.OP, "(")
        args: list[n.Node] = []
        kwargs: dict[str, n.Node] = {}

        while not self._check(TokenType.OP, ")"):
            # `name=` sólo es kwarg si el `=` viene inmediatamente después.
            if (
                self._current.type is TokenType.NAME
                and self._tokens[self._pos + 1].type is TokenType.OP
                and self._tokens[self._pos + 1].value == "="
            ):
                key = self._advance().value
                self._advance()
                kwargs[key] = self._parse_expression()
            else:
                args.append(self._parse_expression())
            if not self._accept(TokenType.OP, ","):
                break

        self._expect(TokenType.OP, ")")
        return n.Call(line=line, func=func, args=args, kwargs=kwargs)

    def _parse_dict(self) -> n.DictLit:
        open_tok = self._expect(TokenType.OP, "{")
        items: list[tuple[str, n.Node]] = []

        while not self._check(TokenType.OP, "}"):
            # La clave puede venir entre comillas: el modelo escribe JSON y
            # Python, y en los dos las claves llevan comillas. Rechazarlas costaba
            # un round-trip de reparación por un detalle cosmético.
            key_tok = self._accept(TokenType.STRING) or self._expect(TokenType.NAME)
            quoted = key_tok.type is TokenType.STRING

            if self._accept(TokenType.OP, ":"):
                items.append((key_tok.value, self._parse_expression()))
            elif quoted:
                raise GlyphSyntaxError(
                    f'la clave "{key_tok.value}" necesita un valor: {{"{key_tok.value}": ...}}',
                    key_tok.line,
                    key_tok.column,
                )
            else:
                # Forma corta: {oem} equivale a {oem: oem}.
                items.append((key_tok.value, n.Name(line=key_tok.line, id=key_tok.value)))
            if not self._accept(TokenType.OP, ","):
                break

        self._expect(TokenType.OP, "}")
        return n.DictLit(line=open_tok.line, items=items)

    def _parse_list(self) -> n.ListLit:
        open_tok = self._expect(TokenType.OP, "[")
        items: list[n.Node] = []
        while not self._check(TokenType.OP, "]"):
            items.append(self._parse_expression())
            if not self._accept(TokenType.OP, ","):
                break
        self._expect(TokenType.OP, "]")
        return n.ListLit(line=open_tok.line, items=items)
