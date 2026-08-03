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
