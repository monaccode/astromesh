import pytest

from astromesh_glyph.errors import GlyphSyntaxError
from astromesh_glyph.syntax.lexer import tokenize
from astromesh_glyph.syntax.tokens import TokenType


def _types(source):
    return [t.type for t in tokenize(source)]


def test_simple_assignment():
    toks = tokenize("x = 1\n")
    assert [(t.type, t.value) for t in toks] == [
        (TokenType.NAME, "x"),
        (TokenType.OP, "="),
        (TokenType.NUMBER, "1"),
        (TokenType.NEWLINE, "\n"),
        (TokenType.EOF, ""),
    ]


def test_blank_lines_and_comments_produce_no_tokens():
    assert _types("\n# comentario\n\nx = 1\n") == [
        TokenType.NAME,
        TokenType.OP,
        TokenType.NUMBER,
        TokenType.NEWLINE,
        TokenType.EOF,
    ]


def test_indent_and_dedent_are_emitted_around_a_block():
    source = "if a:\n    b = 1\nc = 2\n"
    assert _types(source) == [
        TokenType.NAME,
        TokenType.NAME,
        TokenType.OP,
        TokenType.NEWLINE,  # if a :
        TokenType.INDENT,
        TokenType.NAME,
        TokenType.OP,
        TokenType.NUMBER,
        TokenType.NEWLINE,  # b = 1
        TokenType.DEDENT,
        TokenType.NAME,
        TokenType.OP,
        TokenType.NUMBER,
        TokenType.NEWLINE,  # c = 2
        TokenType.EOF,
    ]


def test_dangling_indent_is_closed_at_eof():
    assert _types("if a:\n    b = 1\n")[-2:] == [TokenType.DEDENT, TokenType.EOF]


def test_two_char_operators_are_single_tokens():
    values = [t.value for t in tokenize("a == b\n") if t.type == TokenType.OP]
    assert values == ["=="]


def test_pipe_is_an_operator():
    values = [t.value for t in tokenize("a | b\n") if t.type == TokenType.OP]
    assert values == ["|"]


def test_a_dict_can_span_several_lines():
    """Continuación implícita dentro de corchetes, como Python.

    Sin esto la promesa de "sintaxis familiar" es falsa: el modelo escribe dicts
    multilínea porque es lo natural, y el primer benchmark contra kimi-k2.5 falló
    entero por esto.
    """
    assert _types("return {\n    a: 1,\n    b: 2\n}\n") == [
        TokenType.NAME,  # return
        TokenType.OP,  # {
        TokenType.NAME,
        TokenType.OP,
        TokenType.NUMBER,  # a: 1
        TokenType.OP,  # ,
        TokenType.NAME,
        TokenType.OP,
        TokenType.NUMBER,  # b: 2
        TokenType.OP,  # }
        TokenType.NEWLINE,
        TokenType.EOF,
    ]


def test_a_call_can_span_several_lines():
    assert _types("v = f(\n    a=1,\n    b=2\n)\n") == [
        TokenType.NAME,
        TokenType.OP,  # v =
        TokenType.NAME,
        TokenType.OP,  # f (
        TokenType.NAME,
        TokenType.OP,
        TokenType.NUMBER,  # a=1
        TokenType.OP,  # ,
        TokenType.NAME,
        TokenType.OP,
        TokenType.NUMBER,  # b=2
        TokenType.OP,  # )
        TokenType.NEWLINE,
        TokenType.EOF,
    ]


def test_a_list_can_span_several_lines():
    assert _types("x = [\n  1,\n  2\n]\n").count(TokenType.NEWLINE) == 1


def test_indentation_inside_brackets_produces_no_indent_tokens():
    """La sangría de una continuación es cosmética, no abre un bloque."""
    types = _types("x = f(\n        a=1\n)\n")
    assert TokenType.INDENT not in types
    assert TokenType.DEDENT not in types


def test_a_block_still_works_after_a_multiline_call():
    types = _types("v = f(\n    a=1\n)\nif v.empty:\n    w = g()\n")
    assert types.count(TokenType.INDENT) == 1
    assert types.count(TokenType.DEDENT) == 1


def test_an_unclosed_bracket_is_reported():
    with pytest.raises(GlyphSyntaxError, match="sin cerrar"):
        tokenize("x = f(\n    a=1\n")


def test_a_stray_closing_bracket_is_reported():
    with pytest.raises(GlyphSyntaxError, match="sin abrir"):
        tokenize("x = 1)\n")


def test_a_leading_minus_is_part_of_the_number():
    """Glyph no tiene aritmética, así que `-` sólo puede iniciar un negativo."""
    tok = next(t for t in tokenize("x = -12\n") if t.type == TokenType.NUMBER)
    assert tok.value == "-12"


def test_a_minus_not_followed_by_a_digit_is_rejected():
    with pytest.raises(GlyphSyntaxError, match="inesperado"):
        tokenize("x = a - b\n")


def test_strings_keep_their_content_without_quotes():
    tok = next(t for t in tokenize('x = "hola mundo"\n') if t.type == TokenType.STRING)
    assert tok.value == "hola mundo"


def test_unterminated_string_raises_with_position():
    with pytest.raises(GlyphSyntaxError) as exc:
        tokenize('x = "sin cerrar\n')
    assert exc.value.line == 1


def test_tabs_in_indentation_are_rejected():
    with pytest.raises(GlyphSyntaxError, match="tabulador"):
        tokenize("if a:\n\tb = 1\n")


def test_inconsistent_dedent_is_rejected():
    with pytest.raises(GlyphSyntaxError, match="indentación"):
        tokenize("if a:\n        b = 1\n    c = 2\n")
